"""
Reader para PDFs SmartBrain "Relatório Consolidado de Investimentos".
Usa análise do texto bruto (pdfplumber.extract_text) pois os caracteres
acentuados chegam mangled (U+FFFD) — não há tabelas utilizáveis via
extract_tables para a seção principal.
"""
import io
import re
import unicodedata
from typing import Union

import pdfplumber


# ── Constantes ────────────────────────────────────────────────────────────────
_MESES_PT = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
             'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
_MESES_NAME = {i + 1: m for i, m in enumerate(_MESES_PT)}

_POS_COLS = [
    'saldo_anterior', 'aplicacoes', 'resgates', 'rendimentos',
    'imposto_pago', 'saldo_bruto', 'provisao_ir', 'saldo_liquido',
    'rentabilidade_mes', 'pct_cdi_mes', 'part_pct', 'ganho',
]
# Total row omits rentabilidade_mes and pct_cdi_mes (10 columns)
_TOTAL_COLS = [
    'saldo_anterior', 'aplicacoes', 'resgates', 'rendimentos',
    'imposto_pago', 'saldo_bruto', 'provisao_ir', 'saldo_liquido',
    'part_pct', 'ganho',
]

_STRATEGY_PREFIXES = (
    'ativos', 'fundos', 'renda', 'multi', 'previ', 'rf', 'acao',
    'acoes', 'carteira', 'cdi', 'ibov',
)

# Regex para número no formato brasileiro
_BR_NUM = r'-?(?:\d{1,3}\.)*\d+,\d{2}'
_FIND_NUMS = re.compile(_BR_NUM)


# ── Helpers de texto ──────────────────────────────────────────────────────────

def _br2float(s) -> 'float | None':
    """Converte '1.234,56' ou '(1.234,56)' → float. None se inválido."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in ('-', '—', 'N/A', 'n/a', '--', ''):
        return None
    negativo = s.startswith('(') and s.endswith(')')
    s = s.lstrip('(').rstrip(')')
    s = s.replace('.', '').replace(',', '.')
    s = re.sub(r'[%\s]', '', s)
    try:
        val = float(s)
        return -val if negativo else val
    except ValueError:
        return None


def _norm(text: str) -> str:
    """Strip accents, replacement chars, spaces → lowercase (para comparação)."""
    nfd = unicodedata.normalize('NFD', str(text))
    no_acc = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return re.sub(r'[�\s]', '', no_acc).lower()


def _strip_acc(text: str) -> str:
    """Strip accents e chars de substituição, mantém espaços."""
    nfd = unicodedata.normalize('NFD', str(text))
    no_acc = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return no_acc.replace('�', '')


def _normalize_estrategia(text: str) -> str:
    return re.sub(r'\s+', ' ', str(text).strip())


def _is_strategy_start(line: str) -> bool:
    """True se a linha parece ser cabeçalho de estratégia.

    Cabeçalhos reais ('Previdência', 'Multimercado', 'FundosImobiliários') vêm
    em mixed case. Linhas ALL-UPPERCASE com mesmo prefixo (ex: 'PREVIDÊNCIA',
    'CARTEIRAITAUINTERNACIONALDE') são fragmentos de NOME DE ATIVO — rejeita.
    """
    n = _norm(line)
    if not n.startswith(_STRATEGY_PREFIXES):
        return False
    alpha = [c for c in line if c.isalpha()]
    if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) >= 0.9:
        return False
    return True


def _is_name_continuation(line: str) -> bool:
    """True se a linha parece ser continuação de nome de ativo.

    Rejeita explicitamente headers/footers de página (contêm '/' nas datas
    mas NÃO são continuação de nome). Limita continuações em UPPERCASE a
    ≤12 chars — strings maiores são nomes completos de OUTROS ativos.
    """
    s = line.strip()
    if not s:
        return False
    n = _norm(s)
    # Page header/footer markers — nunca são continuação
    if n.startswith((
        'cliente:', 'dataextrato', 'datainicio', 'indicede',
        'posicaodeativos', 'saldoanterior', 'aplicacoes',
        'ativos', 'bruto', 'compras', 'nomes', 'ativosbr',
        'rentabilidadeno',
    )):
        return False
    if s.startswith('('):  # footer "(31/03/2026) no mês"
        return False
    # UPPER curta (PRIVC, ACCESS, IEFICFI, MULTIMERCADO, PREVIDÊNCIA, etc.) — ≤12 chars,
    # Unicode-aware (aceita acentos como Ê em PREVIDÊNCIA)
    stripped = s.replace(' ', '')
    is_short_upper = (
        2 <= len(stripped) <= 12
        and stripped.isalpha()
        and stripped.isupper()
    )
    return bool(
        '/' in s                     # date codes like 05/2031
        or s[:2].isdigit()           # starts with digits
        or s.lower().startswith('gross')
        or is_short_upper
    )


# ── Classificação de páginas (state-machine) ──────────────────────────────────

def _page_type(text: str) -> str:
    t = _norm(text)
    if 'posicaodeativos' in t or ('saldoanterior' in t and 'saldoliquido' in t):
        return 'posicao_ativos'
    if 'ganhosfinanceiros' in t:
        return 'ganhos_financeiros'
    if 'rentabilidadesmensaisdacarteira' in t:
        return 'rentabilidades_mensais'
    if 'rentabilidadesporestrategia' in t or 'periodosfechados' in t:
        return 'rentabilidades_estrategia'
    if 'disponibilidadefinanceira' in t:
        return 'disponibilidade'
    if 'riscoeretorno' in t:
        return 'risco_retorno'
    return 'unknown'


# ── Extração de cabeçalho ─────────────────────────────────────────────────────

def _extract_header(pages_text: list) -> dict:
    """Extrai metadados do cliente das primeiras páginas."""
    header = {
        'cliente': '',
        'data_extrato': '',
        'data_inicio': '',
        'mes_referencia': '',
        'indice_comparacao': 'CDI',
    }
    # Concatena texto das primeiras 3 páginas
    combined = '\n'.join(pages_text[:3])
    nt = _norm(combined)

    m = re.search(r'cliente:([a-z0-9]+?)(?=dataextrato|datainicio|indicedecomparacao|mesreferencia|$)', nt)
    if m:
        header['cliente'] = m.group(1).upper()

    m = re.search(r'dataextrato:(\d{2}/\d{2}/\d{4})', nt)
    if m:
        header['data_extrato'] = m.group(1)

    m = re.search(r'datainicio:(\d{2}/\d{2}/\d{4})', nt)
    if m:
        header['data_inicio'] = m.group(1)

    for idx in ('cdi', 'ibov', 'ipca', 'ihfa', 'ifix', 'poupanca'):
        if f'indicedecomparacao:{idx}' in nt:
            header['indice_comparacao'] = idx.upper()
            break

    # Mês referência (página 1: "MêsReferência: Outubro-25")
    m = re.search(r'mesreferencia:([a-z]+-\d{2,4})', nt)
    if m:
        raw = m.group(1)
        # Capitaliza primeira letra
        header['mes_referencia'] = raw[0].upper() + raw[1:]

    return header


# ── Posição de Ativos ─────────────────────────────────────────────────────────

# Termos de cabeçalho para ignorar (normalizados)
_POS_SKIP = {
    'posicaodeativos', 'saldoanterior', 'aplicacoes', 'resgates',
    'rendimentos', 'impostonopago', 'provisaodeirios', 'provisaode',
    'saldobruto', 'saldoliquido', 'rentabilidadenomes', 'docdi',
    'part', 'ganho', 'compras', 'vendas', 'proventos', 'pago',
}
# Prefixos de linha a ignorar (normalizados)
_POS_SKIP_PREFIXES = (
    'cliente:', 'dataextrato', 'datainicio', 'indicede',
    'rentabilidade\n', 'ativosbrutosaldo', 'compraven',
    'nos\xa0meses', 'nomes',
)


def _parse_posicao_ativos(pages: list) -> tuple:
    """
    Analisa Posição de Ativos (várias páginas) via texto.
    Retorna (ativos, subtotais, total_dict).
    """
    ativos = []
    subtotais = []
    total_dict = {}
    estrategia_atual = None
    pending = []         # linhas de nome acumuladas
    waiting_strategy = True   # esperando próximo cabeçalho de estratégia
    skip_next_text = False    # pular próxima linha de texto (continuação de label)

    def _build_record(label_parts, nums):
        label = ' '.join(p.strip() for p in label_parts if p.strip())
        nl = _norm(label)
        padded = (nums + [None] * 12)[:12]
        d = dict(zip(_POS_COLS, padded))

        # Verifica sub-total em qualquer parte do label
        if any('subtotal' in _norm(p) or 'sub-total' in p.lower() for p in label_parts if p):
            d['estrategia'] = estrategia_atual
            return 'subtotal', d

        if nl == 'total' or (not nl and len(nums) >= 10):
            # Para total row (10 colunas), remapear
            if len(nums) == 10:
                d10 = dict(zip(_TOTAL_COLS, nums + [None] * 10))
                return 'total', d10
            return 'total', d

        if label:
            d['estrategia'] = estrategia_atual
            d['nome'] = label
            return 'asset', d

        return 'total', d   # sem label = total

    all_lines = []
    for page in pages:
        text = page.extract_text() or ''
        all_lines.extend(text.split('\n'))
        all_lines.append('')  # separador de página

    i = 0
    while i < len(all_lines):
        line = all_lines[i].strip()
        i += 1

        if not line:
            continue

        nl = _norm(line)

        # Pula cabeçalhos de página, colunas e footers
        if (nl.startswith(('cliente:', 'dataextrato', 'datainicio', 'indicede'))
                or nl in _POS_SKIP
                or any(nl.startswith(p) for p in (
                    'posicaodeativos', 'saldoanterior', 'aplicacoes',
                    'compras', 'nomes', 'ativosbr'))
                or line.startswith('(')):  # footer "(31/03/2026) no mês"
            continue

        nums = _FIND_NUMS.findall(line)

        if len(nums) >= 10:
            # Linha de dados
            m = _FIND_NUMS.search(line)
            text_before = line[:m.start()].strip() if m else ''
            num_vals = [_br2float(n) for n in nums[:12]]

            label_parts = pending.copy()
            if text_before:
                label_parts.append(text_before)
            pending = []

            rtype, rec = _build_record(label_parts, num_vals)

            if rtype == 'total':
                total_dict = rec
                skip_next_text = False
                waiting_strategy = False
            elif rtype == 'subtotal':
                subtotais.append(rec)
                skip_next_text = True  # espera continuação do label
                waiting_strategy = False
            else:
                ativos.append(rec)
                skip_next_text = False
                waiting_strategy = False
                # Verifica continuação de nome: apenas a PRIMEIRA linha não-vazia
                # após o data row. Pegar mais que isso confunde com o nome do
                # PRÓXIMO ativo (todos os assets têm no máx. 1 linha de wrap).
                while i < len(all_lines):
                    nxt = all_lines[i].strip()
                    if not nxt:
                        i += 1
                        continue
                    if len(_FIND_NUMS.findall(nxt)) >= 10:
                        break
                    if _is_name_continuation(nxt):
                        rec['nome'] = (rec['nome'] + ' ' + nxt).strip()
                        i += 1
                    break  # única continuação considerada

        elif len(nums) == 0:
            # Linha só de texto

            if skip_next_text:
                # Pode ser continuação de label de sub-total OU nova estratégia
                if _is_strategy_start(line):
                    estrategia_atual = _normalize_estrategia(line)
                    waiting_strategy = False
                # senão: ignora (continuação do label)
                skip_next_text = False

            elif waiting_strategy:
                estrategia_atual = _normalize_estrategia(line)
                waiting_strategy = False

            elif not pending and _is_strategy_start(line):
                # Nova estratégia quando pending está vazio
                estrategia_atual = _normalize_estrategia(line)

            else:
                pending.append(line)

        else:
            # 1-9 números — parte do nome ou linha de transição
            pending.append(line)

    return ativos, subtotais, total_dict


# ── Ganhos Financeiros ────────────────────────────────────────────────────────

def _parse_ganhos_financeiros(pages: list) -> tuple:
    """
    Retorna (ganhos_list, totais_dict).
    Cada linha: StrategyName R$_mes R$_ano R$_inicio
    """
    ganhos = []
    totais = {}

    for page in pages:
        text = page.extract_text() or ''
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            nums = _FIND_NUMS.findall(line)
            if len(nums) < 3:
                continue
            m = _FIND_NUMS.search(line)
            text_before = line[:m.start()].strip() if m else ''
            vals = [_br2float(n) for n in nums[:3]]

            if not text_before:
                continue

            nl = _norm(text_before)
            if nl in ('estrategia', 'nomes', 'nomes', ''):
                continue

            rec = {
                'estrategia': text_before,
                'ganho_mes': vals[0],
                'ganho_ano': vals[1],
                'ganho_inicio': vals[2],
            }

            if nl == 'total':
                totais = {'ganho_mes': vals[0], 'ganho_ano': vals[1], 'ganho_inicio': vals[2]}
            else:
                ganhos.append(rec)

    return ganhos, totais


# ── Rentabilidades Mensais ────────────────────────────────────────────────────

def _parse_rentabilidades_mensais(pages: list) -> list:
    """
    Retorna lista de {ano, mes, ret_pct, pct_cdi}.
    Formato por linha: YEAR  val val val ... (13 tokens = 12 meses + acum.ano)
    """
    result = []
    MESES = _MESES_PT
    # posição 1..12 = Jan..Dez, posição 0 = Ano
    # header: Ano Jan Fev Mar Abr Mai Jun Jul Ago Set Out Nov Dez Rent.Ano

    for page in pages:
        text = page.extract_text() or ''
        lines = text.split('\n')
        month_pos = {}  # col_index → mes_name
        current_year = None

        for line in lines:
            line = line.strip()
            if not line:
                continue
            tokens = line.split()
            first = tokens[0] if tokens else ''

            # Detect header row
            if first.lower() == 'ano' or first in MESES:
                for i, tok in enumerate(tokens):
                    if tok in MESES:
                        month_pos[i] = tok
                continue

            # Year row
            if re.match(r'^\d{4}$', first):
                current_year = int(first)
                for pos, mes_name in month_pos.items():
                    if pos < len(tokens):
                        v = _br2float(tokens[pos])
                        if v is not None:
                            result.append({
                                'ano': current_year,
                                'mes': mes_name,
                                'ret_pct': v,
                                'pct_cdi': None,
                            })
                continue

            # CDI / benchmark row
            first_norm = _norm(first)
            if first_norm.startswith('%') or first_norm.startswith('docdi'):
                if current_year:
                    for pos, mes_name in month_pos.items():
                        if pos < len(tokens):
                            v = _br2float(tokens[pos])
                            if v is not None:
                                for entry in reversed(result):
                                    if entry['ano'] == current_year and entry['mes'] == mes_name:
                                        entry['pct_cdi'] = v
                                        break
                    current_year = None  # reset after CDI row

    return result


# ── Rentabilidades por Estratégia ─────────────────────────────────────────────

def _parse_rentabilidades_estrategia(pages: list) -> list:
    """
    Retorna lista de dicts com ret_mes, bench_mes, ret_ano, bench_ano, etc.
    Benchmark rows use 1-decimal percentages (e.g. 76,6) so token-based parsing
    is used instead of _FIND_NUMS which requires exactly 2 decimal places.
    """
    result = []
    COLS_R = ['ret_mes', 'ret_ano', 'ret_12m', 'ret_24m', 'ret_36m', 'ret_inicio']
    COLS_B = ['bench_mes', 'bench_ano', 'bench_12m', 'bench_24m', 'bench_36m', 'bench_inicio']

    _SKIP_NL = {'estrategia', 'no', 'mes', 'ano', 'desdeo', 'noano', 'meses',
                'cliente:', 'dataextrato', 'datainicio', 'indicede',
                'rentabilidadesporestrategiaemp', 'total'}

    for page in pages:
        text = page.extract_text() or ''
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue

            tokens = line.split()
            nl = _norm(line)

            # Skip header / metadata rows
            if any(nl.startswith(k) for k in _SKIP_NL):
                continue
            if nl in _SKIP_NL:
                continue

            # Split tokens into label (leading non-numeric) + value tokens
            label_toks, val_toks = [], []
            for tok in tokens:
                if not val_toks and tok != '--' and _br2float(tok) is None:
                    label_toks.append(tok)
                else:
                    val_toks.append(tok)

            # Need at least some value tokens (or -- placeholders)
            has_vals = any(tok == '--' or _br2float(tok) is not None for tok in val_toks)
            if not has_vals:
                continue

            label = ' '.join(label_toks).strip()
            nl_label = _norm(label)

            # Skip pure total rows (no label or numeric-only labels)
            if not label or nl_label in _SKIP_NL:
                continue

            # Parse values (-- → None, up to 6 periods)
            vals = []
            for tok in val_toks[:6]:
                vals.append(None if tok == '--' else _br2float(tok))
            padded = (vals + [None] * 6)[:6]

            # Benchmark row for the last strategy
            is_bench = (nl_label.startswith('%') or nl_label.startswith('var')
                        or nl_label.startswith('docdi') or 'variacao' in nl_label)
            if is_bench and result:
                for k, v in zip(COLS_B, padded):
                    result[-1][k] = v
                continue

            # New strategy row
            d = {'estrategia': label}
            for k, v in zip(COLS_R, padded):
                d[k] = v
            for k in COLS_B:
                d[k] = None
            result.append(d)

    return result


# ── Disponibilidade e Risco/Retorno ───────────────────────────────────────────

def _parse_disponibilidade_risco(pages: list) -> tuple:
    """
    Retorna (disponibilidade_list, risco_dict, totais_financeiros_dict).
    """
    disponibilidade = []
    risco = {}
    totais_fin = {}

    DISP_PERIOD_RE = re.compile(r'^de\d+|^acima')
    PERF_PERIOD_RE = re.compile(r'^(\d{2})meses|^desdeo|^noano', re.I)
    COLS_DISP = ['valor', 'pct', 'valor_acum', 'pct_acum', 'valor_liq']
    COLS_PERF = ['carteira', 'cdi', 'pct_indice', 'volat']

    for page in pages:
        text = page.extract_text() or ''
        nt_full = _norm(text)
        periodos = []

        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            nl = _norm(line)
            nums = _FIND_NUMS.findall(line)

            # ── Disponibilidade ──────────────────────────────────────────────
            # Format: <periodo> <valor_br> <pct_int> <valor_acum_br> <pct_acum_int> <valor_liq_br>
            # pct columns are bare integers, not BR decimals → need separate pattern
            if DISP_PERIOD_RE.match(nl):
                _DISP_ROW = re.compile(
                    r'([\d.]+,\d{2})\s+(\d+)\s+([\d.]+,\d{2})\s+(\d+)\s+([\d.]+,\d{2})'
                )
                dm = _DISP_ROW.search(line)
                if dm:
                    d = {
                        'periodo': line.split()[0] if line.split() else nl,
                        'valor': _br2float(dm.group(1)),
                        'pct': float(dm.group(2)),
                        'valor_acum': _br2float(dm.group(3)),
                        'pct_acum': float(dm.group(4)),
                        'valor_liq': _br2float(dm.group(5)),
                    }
                else:
                    vals = [_br2float(n) for n in nums]
                    padded = (vals + [None] * 5)[:5]
                    d = dict(zip(COLS_DISP, padded))
                    d['periodo'] = line.split()[0] if line.split() else nl
                disponibilidade.append(d)
                continue

            # ── Posição Financeira (total saldo) ─────────────────────────────
            if nl.startswith('total') and len(nums) >= 4:
                # Formato: Total saldo_bruto provisao saldo_liq ganho
                if not totais_fin:
                    vals = [_br2float(n) for n in nums[:4]]
                    totais_fin = {
                        'saldo_bruto': vals[0],
                        'provisao_ir': vals[1],
                        'saldo_liquido': vals[2],
                        'ganho_mes': vals[3] if len(vals) > 3 else None,
                    }
                continue

            # ── Risco/Retorno ─────────────────────────────────────────────────
            if 'mesesacima' in nl and nums:
                m2 = re.search(r'(\d+)', line)
                if m2:
                    risco['meses_acima'] = int(m2.group(1))
                m3 = re.search(r'(\d+[,.]?\d*)\s*%', line)
                if m3:
                    risco['pct_acima'] = _br2float(m3.group(1).replace('.', '').replace(',', '.'))

            elif 'mesesabaixo' in nl and nums:
                m2 = re.search(r'(\d+)', line)
                if m2:
                    risco['meses_abaixo'] = int(m2.group(1))

            elif 'maiorrent' in nl and nums:
                m2 = re.search(r'([-\d,]+)%', line)
                m3 = re.search(r'(\w{3}/\d{2})', line)
                if m2:
                    risco['maior_ret'] = _br2float(m2.group(1))
                if m3:
                    risco['maior_ret_data'] = m3.group(1)

            elif 'menorrent' in nl and nums:
                m2 = re.search(r'([-\d,]+)%', line)
                m3 = re.search(r'(\w{3}/\d{2})', line)
                if m2:
                    risco['menor_ret'] = _br2float(m2.group(1))
                if m3:
                    risco['menor_ret_data'] = m3.group(1)

            # ── Períodos de performance ───────────────────────────────────────
            pm = PERF_PERIOD_RE.match(nl)
            if pm and nums:
                # Pode haver contexto antes: "MesesacimadoBenchmark 80 50,3% 03meses 4,15..."
                # Procura o label do período na linha
                period_match = re.search(r'(\d+)\s*meses|desdeo[\w]*inicio|noano', nl)
                if period_match:
                    period_label = re.search(
                        r'(\d+\s*meses|desde\s*o\s*in[íi]cio|no\s*ano)',
                        _strip_acc(line), re.I,
                    )
                    label = period_match.group(0).replace('meses', ' meses').strip()
                    vals = [_br2float(n) for n in nums[:4]]
                    padded = (vals + [None] * 4)[:4]
                    periodos.append({
                        'periodo': label,
                        **dict(zip(COLS_PERF, padded)),
                    })

            # Linha só com 4 BR numbers (períodos sem label na mesma linha)
            elif len(nums) == 4 and not _FIND_NUMS.match(nl[:3]) and periodos:
                # Pode ser uma linha separada para um período
                pass

        # Linha "Desdeoinicio" sem PERF_PERIOD_RE match
        for line in text.split('\n'):
            nl2 = _norm(line.strip())
            if 'desdeo' in nl2 and 'inicio' in nl2:
                nums2 = _FIND_NUMS.findall(line)
                if len(nums2) >= 4:
                    vals = [_br2float(n) for n in nums2[:4]]
                    periodos.append({
                        'periodo': 'Desde o Início',
                        **dict(zip(COLS_PERF, (vals + [None] * 4)[:4])),
                    })
                    break

        if periodos:
            risco['periodos'] = periodos

    return disponibilidade, risco, totais_fin


# ── Entry point ───────────────────────────────────────────────────────────────

def ler_relatorio_consolidado(
    source: 'Union[str, bytes, bytearray]',
    nome_arquivo: str = '',
) -> dict:
    """
    Analisa PDF SmartBrain "Relatório Consolidado de Investimentos".
    source: caminho (str), bytes, bytearray, ou file-like object.
    nome_arquivo: nome do arquivo (fallback para cliente e data).
    Retorna dict estruturado.
    """
    if isinstance(source, (bytes, bytearray)):
        ctx = pdfplumber.open(io.BytesIO(source))
    elif isinstance(source, str):
        ctx = pdfplumber.open(source)
    else:
        ctx = pdfplumber.open(source)

    with ctx as pdf:
        page_records = []
        for page in pdf.pages:
            text = page.extract_text() or ''
            page_records.append((page, text))

        # Cabeçalho das primeiras páginas
        header = _extract_header([t for _, t in page_records[:3]])

        # Fallback: cliente e data do nome do arquivo
        if not header.get('cliente') and nome_arquivo:
            m = re.search(r'-\s*([A-Z0-9]+)\s*(?:\.pdf|$)', nome_arquivo, re.IGNORECASE)
            if m:
                header['cliente'] = m.group(1).upper()
            else:
                parts = re.split(r'[-_]', re.sub(r'\.pdf$', '', nome_arquivo, flags=re.I))
                if parts:
                    header['cliente'] = parts[-1].strip().upper()

        if not header.get('data_extrato') and nome_arquivo:
            m = re.search(r'(\d{2})[./](\d{2})[./](\d{4})', nome_arquivo)
            if m:
                header['data_extrato'] = f"{m.group(1)}/{m.group(2)}/{m.group(3)}"

        # Classifica páginas (state-machine)
        section = 'unknown'
        section_pages: dict = {
            'posicao_ativos': [],
            'ganhos_financeiros': [],
            'rentabilidades_mensais': [],
            'rentabilidades_estrategia': [],
            'disponibilidade': [],
            'risco_retorno': [],
        }

        for page, text in page_records:
            ptype = _page_type(text)
            if ptype != 'unknown':
                section = ptype
            if section in section_pages:
                section_pages[section].append(page)
                # Página com disponibilidade pode ter risco também
                if section == 'disponibilidade' and 'riscoeretorno' in _norm(text):
                    if page not in section_pages['risco_retorno']:
                        section_pages['risco_retorno'].append(page)

        # Parse de cada seção
        ativos, subtotais, total_pos = _parse_posicao_ativos(
            section_pages['posicao_ativos']
        )
        ganhos, totais_ganhos = _parse_ganhos_financeiros(
            section_pages['ganhos_financeiros']
        )
        rent_mensais = _parse_rentabilidades_mensais(
            section_pages['rentabilidades_mensais']
        )
        rent_est = _parse_rentabilidades_estrategia(
            section_pages['rentabilidades_estrategia']
        )

        # Disponibilidade + Risco + Totais financeiros
        disp_pages = list(dict.fromkeys(
            section_pages['disponibilidade'] + section_pages['risco_retorno']
        ))
        disponibilidade, risco, totais_fin = _parse_disponibilidade_risco(disp_pages)

        # Consolida totais (prioriza dados da página de disponibilidade)
        saldo_bruto   = (totais_fin.get('saldo_bruto')
                         or total_pos.get('saldo_bruto'))
        provisao_ir   = (totais_fin.get('provisao_ir')
                         or total_pos.get('provisao_ir'))
        saldo_liquido = (totais_fin.get('saldo_liquido')
                         or total_pos.get('saldo_liquido'))
        ganho_mes     = (totais_ganhos.get('ganho_mes')
                         or totais_fin.get('ganho_mes')
                         or total_pos.get('ganho'))

        return {
            **header,
            'saldo_bruto_total': saldo_bruto,
            'saldo_liquido_total': saldo_liquido,
            'provisao_ir_total': provisao_ir,
            'ganho_mes_total': ganho_mes,
            'ganho_ano_total': totais_ganhos.get('ganho_ano'),
            'ganho_inicio_total': totais_ganhos.get('ganho_inicio'),
            'ativos': ativos,
            'subtotais': subtotais,
            'ganhos_financeiros': ganhos,
            'rentabilidades_estrategia': rent_est,
            'rentabilidades_mensais': rent_mensais,
            'disponibilidade': disponibilidade,
            'risco_retorno': risco,
        }
