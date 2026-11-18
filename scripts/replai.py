#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · a CLI: conta, listas, registro, planilha, coleta, escrita, revisão, postagem.
"""Motor da skill /replai. O Claude conversa e os subagentes escrevem; este script faz o resto.

COMANDOS (todos aceitam --conta; com uma conta só, ela é a padrão). Onde [--rede R] é opcional,
sem ele o comando roda as redes ligadas JUNTAS: um navegador, uma aba por rede, um escritor só.
    checar                                  ambiente, quem opera, sessão, conta, voz e listas
    configurar  --nome N [--operador N --idioma pt|en] [--redes linkedin,x] [--lista link|xlsx]
                [--x-lista URL] [--nunca-citar NOME]... [--pode-citar NOME]...   a primeira vez num comando
    operador    --nome N --idioma pt|en     quem opera este PC (o idioma da conversa e da planilha)
    login       [--rede R]                  abre o Chrome do Replai, uma aba por rede, para logar (segundo plano)
    conta       [--nome N] [--nunca-citar NOME] [--pode-citar NOME]
                [--rede R --ativa sim|nao --modo revisao|sozinho --perfil URL
                 --teto-comentarios N --teto-curtidas N --ignorar-proibida P]
    lista       --rede R --nome N [--planilha link do Google] [--excel arquivo] [--x-lista URL]
                [--prioridade alta|normal] [--ativa sim|nao]
    coletar     [--rede R] [--lista N] [--simular] [--max N]                 (segundo plano)
    lote        [--rede R]                  imprime o pacote do escritor
    escrever    [--rede R] --arquivo saida.json
    revisao     [--rede R]                  fila numerada para o chat
    aprovar     [--rede R] --arquivo decisoes.json
    postar      [--rede R] [--so ID|primeiro] [--simular]                    (segundo plano)
    status
    calibrar    --rede R                    acha os botões em 3 posts, sem clicar (segundo plano)
    testar      [--rede R]                  confere tudo na tela real, sem postar nem clicar (segundo plano)
    voz-amostra [--rede R]                  posts e comentários da própria conta (segundo plano)
    material    --arquivo CAMINHO [--arquivo ...]   textos de apoio da voz (PDF, Word .docx, MD, HTML, TXT)
    copia                                   cópia de segurança dos dados (o instalador faz uma antes de atualizar)
    restaurar   [--arquivo ZIP] [--substituir]       põe os dados de volta (PC novo, pasta apagada)
    voz-pacote  [--rede R] --tipo retrato|aprendizado   (aprendizado pede --rede)
    voz         --rede R --arquivo voz.md   grava nova versão da voz
    sininho                                 liga "todas as publicações" nos perfis do LinkedIn (segundo plano)
    vigia       [--rede R] [--ligar|--desligar]  o agendamento do vigia (Windows ou Mac; um por conta, a cada 5 min)
    vigiar      [--rede R] [--agora]        uma execução do vigia (quem chama é o agendamento)

SAÍDA: JSON no stdout (o Claude lê e resume). Códigos: 0 ok (inclusive "nada a fazer"),
2 configuração ou sessão, 3 navegador ocupado, 4 rodada parada (captcha, limite, conta errada).

ONDE FICA (Documentos\\Replai\\)
    operador.json                            quem opera este PC
    <Conta>\\conta.json · voz-<rede>.md · voz-historico\\ · registro\\<rede>.jsonl · rodada\\<rede>\\
    <Conta>\\Replai - <Conta>.xlsx · cache-linkedin.json · amostra-<rede>.json
Com a campanha de DM no PC, o LinkedIn usa a sessão e a trava dela (Documentos\\Campanha LinkedIn\\).
Uma conta roda num PC só: o registro do que já foi comentado é local.
"""
import argparse
import contextlib
import io
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import dados as D
import lista_csv as LC
import regra as R

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

AQUI = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
REFS = AQUI.parent / "referencias"
LOCK_VALIDADE_SEG = 3 * 3600


class Erro(Exception):
    """Erro com código de saída: 2 configuração/sessão, 3 navegador ocupado, 4 rodada parada."""

    def __init__(self, msg, codigo=2):
        super().__init__(msg)
        self.codigo = codigo


class ErroSessao(Erro):
    """A rede deslogou. Quem levanta anota com `marcar_sessao`: até um login dar certo, o robô não abre
    mais a rede (ver regra.sessao_caida)."""

    def __init__(self, msg):
        super().__init__(msg, 2)


def out(obj):
    print(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False, indent=1), flush=True)


def agora():
    return datetime.now().astimezone()      # o fuso do PC de quem opera


def agora_iso():
    return agora().isoformat(timespec="seconds")


pasta_documentos = D.pasta_documentos
BASE = D.pasta_dados()
CAMPANHA = (Path(os.environ["CAMPANHA_DIR"]) if os.environ.get("CAMPANHA_DIR")
            else pasta_documentos() / "Campanha LinkedIn")
# "Nomes que a conta nunca cita" (a empresa, os clientes): começa vazio; cada conta ajusta a sua
# (conta --nunca-citar / --pode-citar).
NOMES_PADRAO = []   # quem opera diz na configuração (a própria empresa, clientes): referencias/configurar.md
ROTULO = {"linkedin": "LinkedIn", "x": "X"}


def ler_json(caminho, padrao=None):
    try:
        return json.loads(Path(caminho).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def gravar_json(caminho, dado):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    tmp.write_text(json.dumps(dado, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, caminho)


def fechar(ctx):
    try:
        ctx.close()
    except Exception:  # noqa: BLE001
        pass


def operador():
    """Quem opera este PC: {"nome", "idioma"}."""
    return ler_json(BASE / "operador.json", {}) or {}


def idioma():
    """'pt' ou 'en': o idioma da conversa e da planilha de quem opera."""
    return "en" if operador().get("idioma") == "en" else "pt"


# --------------------------------------------------------------------------------------------
# Conta
# --------------------------------------------------------------------------------------------
def pasta_da(nome):
    """'Lúcia Prado' -> 'Lucia' (a pasta da conta)."""
    primeiro = (R.sem_acento(nome).strip().split() or ["Conta"])[0]
    return re.sub(r"[^A-Za-z0-9-]", "", primeiro).capitalize() or "Conta"


def contas():
    if not BASE.exists():
        return []
    return sorted(p.name for p in BASE.iterdir() if (p / "conta.json").exists())


def resolver_conta(pedida):
    todas = contas()
    if not pedida:
        if len(todas) == 1:
            return todas[0]
        raise Erro("nenhuma conta criada (use: conta --nome \"Nome Sobrenome\")" if not todas
                   else f"diga qual conta: {', '.join(todas)}")
    alvo = R.sem_acento(pedida).casefold()
    for c in todas:
        if c.casefold() == alvo or alvo.startswith(c.casefold()):
            return c
    raise Erro(f"a conta '{pedida}' não existe (contas: {', '.join(todas) or 'nenhuma'})")


def arq(pasta, *partes):
    return BASE.joinpath(pasta, *partes)


def ler_conta(pasta):
    c = ler_json(arq(pasta, "conta.json"))
    if not c:
        raise Erro(f"conta.json ilegível em {arq(pasta)}")
    return c


def gravar_conta(pasta, c):
    gravar_json(arq(pasta, "conta.json"), c)


def conta_nova(nome):
    rede = lambda ativa, sessao: {"ativa": ativa, "sessao": sessao, "perfil": "", "modo": "revisao",  # noqa: E731
                                  "teto": {}, "proibidas_ignorar": []}
    # Com a campanha de DM no PC, o LinkedIn usa o login dela (loga uma vez só).
    sessao_li = "campanha" if (CAMPANHA / "_navegador").exists() else "propria"
    return {"nome": nome, "nomes_que_nunca_cita": list(NOMES_PADRAO),
            "redes": {"linkedin": rede(True, sessao_li), "x": rede(False, "propria")}, "listas": []}


def rede_cfg(c, rede):
    cfg = (c.get("redes") or {}).get(rede)
    if not cfg or not cfg.get("ativa"):
        raise Erro(f"a rede {rede} não está ligada nesta conta (conta --rede {rede} --ativa sim)")
    return cfg


def carregar(args):
    pasta = resolver_conta(getattr(args, "conta", None))
    return pasta, ler_conta(pasta)


def redes_pedidas(c, rede=None):
    """A rede pedida ou, sem --rede, as ligadas na conta (rodam juntas, no mesmo navegador)."""
    if rede:
        rede_cfg(c, rede)
        return [rede]
    redes = [r for r in R.REDES if ((c.get("redes") or {}).get(r) or {}).get("ativa")]
    if not redes:
        raise Erro("nenhuma rede ligada nesta conta (conta --rede linkedin --ativa sim)")
    return redes


def erro_dict(e):
    return {"erro": str(e), "codigo": e.codigo}


def saida_redes(pedida, res):
    """Com --rede, a saída daquela rede; sem, {rede: saída}. O código é o pior entre as redes."""
    out(res[pedida] if pedida else res)
    return max((r.get("codigo", 2) if r.get("erro") else (4 if r.get("parou") else 0) for r in res.values()),
               default=0)


def nomes_da_conta(c):
    return c.get("nomes_que_nunca_cita") or []


# --------------------------------------------------------------------------------------------
# Registro (journal): a prova do que saiu. Grava ANTES de seguir (fsync), como a campanha.
# --------------------------------------------------------------------------------------------
def registro_de(pasta, rede):
    return arq(pasta, "registro", f"{rede}.jsonl")


def registrar(pasta, rede, ev, **campos):
    linha = {"quando": agora_iso(), "ev": ev}
    linha.update({k: v for k, v in campos.items() if v is not None})
    caminho = registro_de(pasta, rede)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return linha


def marcar_sessao(pasta, rede, ok):
    """Anota a queda ou a volta da sessão, só quando muda (o vigia passa aqui a cada execução)."""
    if R.sessao_caida(eventos(pasta, rede)) == ok:
        registrar(pasta, rede, "sessao_ok" if ok else "sessao_caiu")


def erro_x(pasta, e, onde):
    """O erro de leitura do X: a sessão caída fica anotada; o resto para a rodada."""
    if e.tipo == "SESSAO":
        marcar_sessao(pasta, "x", False)
        return ErroSessao(f"{onde}: {e}")
    return Erro(f"{onde}: {e}", 4)


_LIDOS = {}   # registro -> (arquivo, bytes já lidos, eventos)


def _linhas_json(dado):
    saida = []
    for linha in dado.decode("utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if linha:
            try:
                saida.append(json.loads(linha))
            except ValueError:
                continue
    return saida


def eventos(pasta, rede):
    """Os eventos do registro. Ele só cresce (uma linha por leitura e por execução do vigia) e é lido
    muitas vezes por execução: guarda o que já leu e lê só o que entrou depois. Arquivo trocado ou
    menor: lê de novo do começo."""
    caminho = registro_de(pasta, rede)
    try:
        st = caminho.stat()
    except OSError:
        _LIDOS.pop(str(caminho), None)
        return []
    arquivo, lidos, saida = _LIDOS.get(str(caminho), (None, 0, []))
    if arquivo != (st.st_dev, st.st_ino) or st.st_size < lidos:
        lidos, saida = 0, []
    if st.st_size == lidos:
        return list(saida)
    with open(caminho, "rb") as fh:
        fh.seek(lidos)
        novo = fh.read()
    fim = novo.rfind(b"\n") + 1                 # a linha pela metade não entra na memória
    saida = saida + _linhas_json(novo[:fim])
    _LIDOS[str(caminho)] = ((st.st_dev, st.st_ino), lidos + fim, saida)
    return saida + _linhas_json(novo[fim:])


# --------------------------------------------------------------------------------------------
# Sessão e trava. Conta com `sessao: campanha` (a campanha de DM existe no PC): a MESMA sessão e a
# MESMA trava da campanha, para logar uma vez e DM e Replai nunca abrirem o mesmo LinkedIn juntos.
# --------------------------------------------------------------------------------------------
def _da_campanha(c):
    return ((c.get("redes") or {}).get("linkedin") or {}).get("sessao") == "campanha"


def sessao_de(pasta, c, rede):
    """UM navegador por conta, para as duas redes: quem opera loga no LinkedIn e no X na mesma janela,
    uma vez. Com a campanha de DM no PC, é o navegador dela."""
    rede_cfg(c, rede)
    if _da_campanha(c):
        return CAMPANHA / "_navegador"
    novo, antigo = arq(pasta, "navegador"), arq(pasta, "linkedin-navegador")
    if not novo.exists() and antigo.exists():  # até 27/10 cada rede tinha o seu: o LinkedIn segue logado
        antigo.rename(novo)
    return novo


def trava_de(pasta, c, rede):
    """A trava é do navegador: as duas redes (e a campanha) nunca abrem o mesmo perfil juntas."""
    rede_cfg(c, rede)
    return CAMPANHA / ".enviando.lock" if _da_campanha(c) else arq(pasta, ".navegador.lock")


class Trava:
    """Mesma regra da campanha de DM: arquivo tocado há menos de 3h = ocupado."""

    def __init__(self, caminho):
        self.caminho = Path(caminho)

    def __enter__(self):
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        if self.caminho.exists() and time.time() - self.caminho.stat().st_mtime < LOCK_VALIDADE_SEG:
            raise Erro("o navegador desta rede está ocupado por outra rodada (Replai ou campanha). "
                       f"Se tiver certeza de que nada está rodando, apague {self.caminho}", 3)
        self.caminho.write_text(f"{os.getpid()} {agora_iso()} replai", encoding="utf-8")
        return self

    def tocar(self):
        try:
            self.caminho.touch()
        except OSError:
            pass

    def __exit__(self, *exc):
        try:
            self.caminho.unlink()
        except OSError:
            pass


# --------------------------------------------------------------------------------------------
# Rodada: o pool de candidatos (real e simulação separados)
# --------------------------------------------------------------------------------------------
def rodada_dir(pasta, rede):
    return arq(pasta, "rodada", rede)


def pool(pasta, rede, simular):
    return rodada_dir(pasta, rede) / ("simulacao.json" if simular else "candidatos.json")


def rodada_atual(pasta, rede):
    """(simular, dados do pool) da última coleta."""
    sim = bool((ler_json(rodada_dir(pasta, rede) / "atual.json", {}) or {}).get("simular"))
    return sim, ler_json(pool(pasta, rede, sim))


# --------------------------------------------------------------------------------------------
# Voz e aprendizado
# --------------------------------------------------------------------------------------------
# As seções do arquivo de voz, em PT e em EN (a voz é escrita no idioma de quem opera).
SECOES_VOZ = (("## Quem fala", "## Who speaks"), ("## Assuntos com propriedade", "## Topics of authority"),
              ("## Evitar", "## Avoid"), ("## Tom", "## Tone"), ("## Forma", "## Form"),
              ("## Usa / Nunca usa", "## Uses / Never uses"), ("## Regras aprendidas", "## Learned rules"),
              ("## Exemplos aprovados", "## Approved examples"))
VOZ_MAX_CHARS = 5000
RX_VERSAO = re.compile(r"(?:vers[aã]o|version)\s+(\d+)", re.I)


def voz_arq(pasta, rede):
    return arq(pasta, f"voz-{rede}.md")


def voz_atual(pasta, rede):
    p = voz_arq(pasta, rede)
    return p.read_text(encoding="utf-8") if p.exists() else None


def versao_voz(pasta, rede):
    t = voz_atual(pasta, rede)
    m = RX_VERSAO.search(t.splitlines()[0]) if t else None
    return int(m.group(1)) if m else 0


def data_da_voz(pasta, rede):
    """Quando a voz atual foi gravada pelo comando `voz` (o aprendizado conta dali em diante)."""
    q = None
    for e in eventos(pasta, rede):
        if e.get("ev") == "voz":
            q = e.get("quando")
    return q


def emoji_permitido(voz):
    for linha in (voz or "").splitlines():
        low = linha.lower()
        if "emoji" in low:
            return (not re.search(r"\b(nunca|nenhum|never|none)\b", low)
                    and bool(re.search(r"\b(sim|espor[aá]dico|[aà]s vezes|yes|occasional|sometimes)\b", low)))
    return False


def pares_de_edicao(evs, desde=None):
    return [(e["antes"], e["depois"]) for e in evs
            if e.get("ev") == "editado" and e.get("antes") and e.get("depois")
            and (not desde or e.get("quando", "") >= desde)]


def proibidas(c, rede, evs):
    ign = ((c.get("redes") or {}).get(rede) or {}).get("proibidas_ignorar") or []
    return R.proibidas_aprendidas(pares_de_edicao(evs), ignorar=ign)


def limpar_texto(t, n):
    t = re.sub(r"https?://\S+", "", t or "").replace("#", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:n] + ("…" if len(t) > n else "")


def idade_txt(data, ref):
    h = R.idade_h({"data": data}, ref)
    if h is None:
        return "?"
    return f"{int(h)}h" if h < 48 else f"{int(h // 24)}d"


# --------------------------------------------------------------------------------------------
# Planilha. O registro manda; a planilha é reescrita a partir dele e tolera o Excel aberto.
# --------------------------------------------------------------------------------------------
# Rótulos da planilha no idioma de quem opera. Por dentro, as colunas têm o nome canônico (o PT da
# lista; "Rede", "Post" e "Nota" nas Ações): ALIASES leva qualquer cabeçalho, PT ou EN, até ele.
TXT = {
    "pt": {"resumo": "Resumo", "acoes": "Ações",
           "lista": ["Nome", "Perfil", "Prioridade", "Incluir", "Observação", "Origem", "Último comentário"],
           "acoes_cols": ["Data/hora", "Rede", "Fonte", "Autor", "Post", "Trecho", "Ação", "Comentário",
                          "Link do comentário", "Situação", "Voz", "Nota da revisão"],
           "resumo_cols": ["Rede", "Modo", "Comentários hoje", "Curtidas hoje", "Comentários 7 dias",
                           "Esperando revisão", "Na fila", "Situação"],
           "acao": {"comentado": "comentou", "incerto": "comentou (incerto)", "curtiu": "curtiu"},
           "estado": {},
           "importado": "importado em {}", "atualizado": "Atualizado em {} a partir do registro."},
    "en": {"resumo": "Summary", "acoes": "Actions",
           "lista": ["Name", "Profile", "Priority", "Include", "Notes", "Source", "Last comment"],
           "acoes_cols": ["Date/time", "Network", "Source", "Author", "Post", "Excerpt", "Action", "Comment",
                          "Comment link", "Status", "Voice", "Review note"],
           "resumo_cols": ["Network", "Mode", "Comments today", "Likes today", "Comments 7 days",
                           "Awaiting review", "Queued", "Status"],
           "acao": {"comentado": "commented", "incerto": "commented (uncertain)", "curtiu": "liked"},
           "estado": {"comentado": "commented", "incerto": "uncertain", "comentando": "uncertain",
                      "pulado": "skipped", "aprovado": "approved", "rascunho": "draft",
                      "ja_comentado": "already commented", "vencido": "expired",
                      "descartado": "discarded", "selecionado": "selected"},
           "importado": "imported on {}", "atualizado": "Updated {} from the log."},
}
ALIASES = {
    "nome": "Nome", "name": "Nome", "nome completo": "Nome", "full name": "Nome",
    "pessoa": "Nome", "person": "Nome", "nome da pessoa": "Nome", "contato": "Nome", "contact": "Nome",
    "perfil": "Perfil", "profile": "Perfil", "url": "Perfil",
    "prioridade": "Prioridade", "priority": "Prioridade", "incluir": "Incluir", "include": "Incluir",
    "observação": "Observação", "observacao": "Observação", "obs": "Observação", "notes": "Observação",
    "origem": "Origem", "source": "Origem", "último comentário": "Último comentário",
    "last comment": "Último comentário", "rede": "Rede", "network": "Rede", "post": "Post",
    "nota da revisão": "Nota", "review note": "Nota",
}
NAO = ("não", "nao", "n", "no", "0", "false")


chave_perfil = LC.chave_perfil      # a identidade do perfil: a vanity no LinkedIn, o @ no X


def planilha_de(pasta):
    return arq(pasta, f"Replai - {pasta}.xlsx")


def aba_da_lista(rede, nome):
    return f"{'LinkedIn' if rede == 'linkedin' else 'X'} - {nome}"[:31]


def abrir_planilha(pasta):
    from openpyxl import Workbook, load_workbook
    caminho = planilha_de(pasta)
    if caminho.exists():
        return load_workbook(caminho)
    wb = Workbook()
    wb.active.title = TXT[idioma()]["resumo"]
    return wb


def salvar_planilha(wb, pasta):
    try:
        planilha_de(pasta).parent.mkdir(parents=True, exist_ok=True)
        wb.save(planilha_de(pasta))
        return True
    except PermissionError:
        return False


def _cabecalho(ws, cols):
    from openpyxl.styles import Font, PatternFill
    for i, col in enumerate(cols, 1):
        cel = ws.cell(row=1, column=i, value=col)
        cel.font = Font(bold=True, color="FFFFFF")
        cel.fill = PatternFill("solid", fgColor="1F3A5F")
    ws.freeze_panes = "A2"


def cabecalho(ws):
    """O cabeçalho da aba com os nomes canônicos (a planilha pode estar em PT ou EN)."""
    return [ALIASES.get(str(c.value).strip().lower(), c.value) if c.value else None for c in ws[1]]


def linhas_da_aba(ws):
    cab = cabecalho(ws)
    saida = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = {cab[i]: ("" if v is None else str(v)) for i, v in enumerate(row) if i < len(cab) and cab[i]}
        if any(d.values()):
            saida.append(d)
    return saida


RX_GOOGLE = re.compile(r"docs\.google\.com/spreadsheets/d/([\w-]+)")
PLANILHA_VALE_MIN = 60          # a cópia da planilha do Google se renova a cada hora


def url_exportacao(url):
    """Link do Google Sheets -> o link que baixa a aba como CSV (a aba do #gid=, ou a primeira)."""
    m = RX_GOOGLE.search(url or "")
    if not m:
        return None
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return (f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv"
            + (f"&gid={gid.group(1)}" if gid else ""))


def baixar_planilha(url):
    """O CSV da planilha do Google. Só funciona com 'qualquer pessoa com o link pode ver': sem isso o
    Google devolve a página de login (HTML) e o Replai avisa."""
    import urllib.request
    try:
        with urllib.request.urlopen(url_exportacao(url), timeout=30) as r:
            tipo, corpo = r.headers.get("Content-Type", ""), r.read().decode("utf-8-sig", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise Erro(f"não consegui baixar a planilha do Google ({type(e).__name__}): confira o link e se ela "
                   "está compartilhada como 'qualquer pessoa com o link pode ver'")
    if "text/csv" not in tipo and corpo.lstrip().startswith("<"):
        raise Erro("a planilha do Google não está aberta para quem tem o link: compartilhe como 'qualquer "
                   "pessoa com o link pode ver' (ou baixe como .xlsx e mande o arquivo)")
    return corpo


def linhas_csv(texto):
    import csv
    import io
    try:
        dialeto = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t")
    except csv.Error:
        dialeto = csv.excel
    return list(csv.reader(io.StringIO(texto), dialeto))


# A coluna do perfil de cada rede: pelo nome da coluna e, sem nome claro, pelo conteúdo. Uma planilha
# com coluna de LinkedIn e coluna de X serve às duas redes (uma lista em cada, com o mesmo link).
RX_COL_REDE = {"linkedin": re.compile(r"linkedin", re.I),
               "x": re.compile(r"^\s*(x|@|handle|x handle|twitter|twitter handle|x/twitter|perfil no x|@ no x)\s*$|twitter", re.I)}
RX_VALOR_REDE = {"linkedin": re.compile(r"linkedin\.com/in/", re.I),
                 "x": re.compile(r"(x|twitter)\.com/\w|^\s*@\w{1,15}\s*$", re.I)}


def coluna_do_perfil(cab_bruto, linhas, rede):
    """Índice da coluna com o perfil da rede (ou de qualquer rede, quando `rede` é None), ou None."""
    redes = [rede] if rede else ["linkedin", "x"]
    for r in redes:
        for i, nome in enumerate(cab_bruto):
            if RX_COL_REDE[r].search(str(nome or "")):
                return i
    pontos = [sum(1 for ln in linhas if i < len(ln) and any(RX_VALOR_REDE[r].search(ln[i] or "") for r in redes))
              for i in range(len(cab_bruto))]
    return pontos.index(max(pontos)) if pontos and max(pontos) else None


def ler_tabela(caminho, rede=None):
    """.xlsx, .csv ou link do Google Sheets -> dicts com as colunas padrão (Nome, Perfil, ...). O
    Perfil é a coluna da `rede` (LinkedIn ou X). Linha sem perfil sai."""
    if RX_GOOGLE.search(str(caminho)):
        linhas = linhas_csv(baixar_planilha(str(caminho)))
    elif Path(caminho).suffix.lower() == ".csv":
        linhas = linhas_csv(Path(caminho).read_text(encoding="utf-8-sig"))
    else:
        caminho = Path(caminho)
        from openpyxl import load_workbook
        wb = load_workbook(caminho, read_only=True, data_only=True)
        linhas = [["" if v is None else str(v) for v in r] for r in wb.worksheets[0].iter_rows(values_only=True)]
        wb.close()
    if not linhas:
        return []
    cab = [ALIASES.get(str(x).strip().lower(), str(x).strip()) for x in linhas[0]]
    i = coluna_do_perfil(linhas[0], linhas[1:], rede)
    if i is None and "Perfil" not in cab:
        raise Erro(f"não achei a coluna com o perfil do {rede or 'LinkedIn ou X'}; colunas: {linhas[0]}")
    if i is not None:
        cab = [("Perfil (outra)" if c == "Perfil" else c) for c in cab]
        cab[i] = "Perfil"
    saida = []
    for r in linhas[1:]:
        d = {cab[i]: (r[i] or "").strip() for i in range(min(len(cab), len(r)))}
        if d.get("Perfil"):
            saida.append(d)
    return saida


def importar_lista(pasta, rede, nome, arquivo):
    """Junta as linhas do Excel/CSV na aba da lista; perfil já presente não duplica. (novos, já)."""
    novos = ler_tabela(arquivo, rede)
    wb = abrir_planilha(pasta)
    aba = aba_da_lista(rede, nome)
    if aba in wb.sheetnames:
        ws = wb[aba]
    else:
        ws = wb.create_sheet(aba)
        _cabecalho(ws, TXT[idioma()]["lista"])
    existentes = {chave_perfil(rede, d.get("Perfil")) for d in linhas_da_aba(ws)}
    n = ja = 0
    for d in novos:
        k = chave_perfil(rede, d.get("Perfil"))
        if not k or k in existentes:
            ja += 1
            continue
        existentes.add(k)
        inc = (d.get("Incluir") or "Sim").strip().lower()
        ws.append([d.get("Nome", ""), d["Perfil"], (d.get("Prioridade") or "normal").lower(),
                   "Não" if inc in NAO else "Sim", d.get("Observação", ""),
                   TXT[idioma()]["importado"].format(agora().date().isoformat()), ""])
        n += 1
    if not salvar_planilha(wb, pasta):
        raise Erro("a planilha está aberta no Excel: feche e rode de novo")
    return n, ja


def linhas_do_google(pasta, url, rede, forcar=False):
    """As linhas da planilha do Google, pela cópia local quando ela tem menos de uma hora. Se o Google
    não responder, segue com a última cópia (a rodada não para por isso)."""
    cache = ler_json(arq(pasta, "cache-listas.json"), {}) or {}
    chave = f"{rede} {url}"
    atual = cache.get(chave) or {}
    limite = (agora() - timedelta(minutes=PLANILHA_VALE_MIN)).isoformat()
    if atual.get("linhas") is not None and not forcar and atual.get("quando", "") >= limite:
        return atual["linhas"]
    try:
        linhas = ler_tabela(url, rede)
    except Erro:
        if atual.get("linhas") is not None and not forcar:
            return atual["linhas"]
        raise
    cache[chave] = {"quando": agora_iso(), "linhas": linhas}
    gravar_json(arq(pasta, "cache-listas.json"), cache)
    return linhas


def arquivo_csv(pasta, li=None):
    """O CSV da lista (o padrão é Documentos/Replai/<Conta>/lista.csv)."""
    return Path(li["csv"]) if li and li.get("csv") else arq(pasta, "lista.csv")


def linhas_do_csv(pasta, li):
    """As linhas do CSV local para a rede da lista, relidas a cada vez (é a fonte da verdade)."""
    caminho = arquivo_csv(pasta, li)
    if not caminho.exists():
        raise Erro(f"a lista CSV sumiu: {caminho} (recrie com: lista --nome {li['nome']} --csv)")
    col = "LinkedIn" if li["rede"] == "linkedin" else "X"
    return [{"Nome": ln["Nome"], "Perfil": ln[col], "Prioridade": ln["Prioridade"], "Incluir": ln["Incluir"],
             "Observação": ln["Observação"]} for ln in LC.ler(caminho) if ln.get(col)]


def linhas_da_lista(pasta, li, wb):
    """As linhas de uma lista: do CSV local, da planilha do Google (quando a lista tem link) ou da aba
    local da planilha do Replai (listas antigas)."""
    if li.get("csv"):
        return linhas_do_csv(pasta, li)
    if li.get("planilha"):
        return linhas_do_google(pasta, li["planilha"], li["rede"])
    aba = aba_da_lista(li["rede"], li["nome"])
    return linhas_da_aba(wb[aba]) if aba in wb.sheetnames else []


def perfis_da_rede(pasta, c, rede, so_lista=None):
    """[{chave, nome, perfil, lista, prioridade}] das listas ativas da rede (Incluir = Sim)."""
    wb = abrir_planilha(pasta)
    saida, vistos = [], set()
    for li in c.get("listas") or []:
        if li["rede"] != rede or not li.get("ativa", True):
            continue
        if so_lista and R.sem_acento(li["nome"]).casefold() != R.sem_acento(so_lista).casefold():
            continue
        for d in linhas_da_lista(pasta, li, wb):
            if (d.get("Incluir") or "Sim").strip().lower() in NAO:
                continue
            k = chave_perfil(rede, d.get("Perfil"))
            if not k or k in vistos:
                continue
            vistos.add(k)
            pri = (d.get("Prioridade") or li.get("prioridade") or "normal").strip().lower()
            saida.append({"chave": k, "nome": d.get("Nome") or k, "perfil": d.get("Perfil"),
                          "lista": li["nome"], "prioridade": "alta" if pri == "alta" else "normal"})
    return saida


def status_da_rede(pasta, c, rede):
    cfg = c["redes"][rede]
    evs = eventos(pasta, rede)
    reg = R.estados(evs)
    t = agora()
    pausada, corte = R.situacao_paradas(evs, t)
    cot = R.cotas(rede, t, evs, cfg.get("teto"))
    sete = t.timestamp() - 7 * 86400
    c7 = sum(1 for r in reg.values() if r["estado"] in ("comentado", "incerto", "comentando")
             and (R.data_de(r.get("comentou_em")) or t).timestamp() >= sete)
    situacao = ("pausada até amanhã (parada hoje)" if pausada
                else "teto pela metade (2 paradas em 7 dias)" if corte else (cot["motivo"] or "pronta"))
    return {"modo": cfg.get("modo"), "hoje": R.contagens(evs, t), "cota_agora": cot,
            "comentarios_7d": c7,
            "esperando_revisao": sum(1 for r in reg.values() if r["estado"] == "rascunho"),
            "na_fila": sum(1 for r in reg.values() if r["estado"] == "aprovado"),
            "voz": versao_voz(pasta, rede), "proibidas": proibidas(c, rede, evs),
            "propor_sozinho": cfg.get("modo") == "revisao" and R.propor_sozinho(evs),
            "vigia": bool(cfg.get("vigia")), "ultimo_vigia": ultimo_vigia(pasta, rede),
            "situacao": situacao}


def montar_resumo(wb, pasta, c):
    from openpyxl.styles import Font
    tx = TXT[idioma()]
    for nome in ("Resumo", "Summary"):
        if nome in wb.sheetnames:
            del wb[nome]
    rs = wb.create_sheet(tx["resumo"], 0)
    rs["A1"] = f"Replai · {c.get('nome', pasta)}"
    rs["A1"].font = Font(bold=True, size=14)
    rs["A2"] = tx["atualizado"].format(agora().strftime('%d/%m/%Y %H:%M'))
    rs.append([])
    rs.append(tx["resumo_cols"])
    for cel in rs[4]:
        cel.font = Font(bold=True)
    for rede in R.REDES:
        if not ((c.get("redes") or {}).get(rede) or {}).get("ativa"):
            continue
        st = status_da_rede(pasta, c, rede)
        rs.append(["LinkedIn" if rede == "linkedin" else "X", st["modo"], st["hoje"]["comentarios_dia"],
                   st["hoje"]["curtidas_dia"], st["comentarios_7d"], st["esperando_revisao"],
                   st["na_fila"], st["situacao"]])
    for col, w in zip("ABCDEFGH", (14, 10, 18, 14, 18, 18, 10, 40)):
        rs.column_dimensions[col].width = w


def sincronizar_planilha(pasta, c):
    """Reescreve a aba Ações a partir do registro, guardando a Nota da revisão, e transforma nota nova
    em evento 'nota' (aprendizado). Atualiza o Último comentário das listas e o Resumo.
    Excel aberto: devolve False e nada se perde (o registro tem tudo)."""
    tx = TXT[idioma()]
    wb = abrir_planilha(pasta)
    notas = {}
    for nome in ("Ações", "Actions"):
        if nome in wb.sheetnames:
            for d in linhas_da_aba(wb[nome]):
                if d.get("Nota") and d.get("Post"):
                    notas[(d.get("Rede"), d["Post"])] = d["Nota"]
            del wb[nome]
    ws = wb.create_sheet(tx["acoes"])
    _cabecalho(ws, tx["acoes_cols"])
    ultimos, linhas = {}, []
    for rede in R.REDES:
        if not ((c.get("redes") or {}).get(rede) or {}).get("ativa"):
            continue
        rotulo = "LinkedIn" if rede == "linkedin" else "X"
        evs = eventos(pasta, rede)
        ja_notas = {(e.get("id"), e.get("nota")) for e in evs if e.get("ev") == "nota"}
        for pid, r in R.estados(evs).items():
            comentou = r["estado"] in ("comentado", "incerto", "comentando")
            acao = ((tx["acao"]["comentado"] if r["estado"] == "comentado" else tx["acao"]["incerto"])
                    if comentou else (tx["acao"]["curtiu"] if r["curtiu"] else None))
            if not acao:
                continue
            nota = notas.get((rotulo, r.get("url")), "")
            if nota and (pid, nota) not in ja_notas:
                registrar(pasta, rede, "nota", id=pid, nota=nota, texto=r.get("texto"))
            if r.get("comentou_em") and r.get("autor"):
                k = (rede, r["autor"])
                ultimos[k] = max(ultimos.get(k, ""), r["comentou_em"][:10])
            quando = (r.get("comentou_em") or r.get("selecionado_em") or "")[:16].replace("T", " ")
            linhas.append([quando, rotulo, r.get("fonte", ""), r.get("nome") or r.get("autor", ""),
                           r.get("url", ""), r.get("trecho", ""), acao,
                           r.get("texto") if comentou else "", r.get("link", ""),
                           tx["estado"].get(r["estado"], r["estado"]),
                           r.get("voz", ""), nota])
    for linha in sorted(linhas, key=lambda x: x[0], reverse=True):
        ws.append(linha)
    for li in c.get("listas") or []:
        aba = aba_da_lista(li["rede"], li["nome"])
        if aba not in wb.sheetnames:
            continue
        wl = wb[aba]
        cab = cabecalho(wl)
        if "Perfil" not in cab or "Último comentário" not in cab:
            continue
        ip, iu = cab.index("Perfil"), cab.index("Último comentário")
        for row in wl.iter_rows(min_row=2):
            k = (li["rede"], chave_perfil(li["rede"], row[ip].value or ""))
            if k in ultimos:
                row[iu].value = ultimos[k]
    montar_resumo(wb, pasta, c)
    return salvar_planilha(wb, pasta)


# --------------------------------------------------------------------------------------------
# Comandos sem navegador
# --------------------------------------------------------------------------------------------
def cmd_checar(args):
    r = {"python": sys.version.split()[0], "pasta": str(BASE), "openpyxl": False, "playwright": False,
         "chrome": False, "chromium_playwright": False}
    try:
        import openpyxl  # noqa: F401
        r["openpyxl"] = True
    except ImportError:
        pass
    try:
        import playwright  # noqa: F401
        r["playwright"] = True
    except ImportError:
        pass
    r["chrome"] = bool(caminho_chrome())
    pw_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or
                  (Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"))
    r["chromium_playwright"] = pw_dir.exists() and any(pw_dir.glob("chromium-*"))
    r["claude_code_caminho"] = caminho_claude()    # o vigia escreve por ele; o login usa este caminho
    r["claude_code"] = bool(r["claude_code_caminho"])
    falta = []
    if sys.version_info < (3, 9):
        falta.append("Python 3.9 ou mais novo")
    if not r["openpyxl"] or not r["playwright"]:
        falta.append("bibliotecas: rode o instalador em modo silencioso")
    if not r["chrome"] and not r["chromium_playwright"]:
        falta.append("navegador: rode o instalador em modo silencioso")
    r["operador"] = operador()
    if not r["operador"].get("nome"):
        falta.append("quem opera: rode 'operador --nome \"Nome\" --idioma pt' (ou en)")
    r["contas"] = contas()
    if not r["contas"]:
        falta.append("conta: crie com 'conta --nome \"Nome Sobrenome\"'")
    else:
        try:
            pasta, c = carregar(args)
            r["conta"] = pasta
            for rede, cfg in c["redes"].items():
                if not cfg.get("ativa"):
                    continue
                ses = sessao_de(pasta, c, rede)
                d = {"sessao_salva": ses.exists() and any(ses.iterdir()), "voz": versao_voz(pasta, rede),
                     "listas": sum(1 for li in c.get("listas", []) if li["rede"] == rede and li.get("ativa", True)),
                     "modo": cfg.get("modo"), "vigia": bool(cfg.get("vigia"))}
                r[rede] = d
                if d["vigia"] and not r["claude_code"]:
                    falta.append("Claude Code de linha de comando (o vigia precisa): rode o instalador do Replai")
                if not d["sessao_salva"]:
                    falta.append(f"login no {rede}: rode 'login' (uma janela, uma aba por rede)")
                if not d["listas"]:
                    falta.append(f"lista do {rede}: 'configurar' ou 'lista --rede {rede} --nome Principal --planilha <link>'")
                if not d["voz"]:
                    falta.append(f"voz do {rede}: roteiro de voz (referencias/voz.md)")
        except Erro as e:
            falta.append(str(e))
    r["falta"] = falta
    r["pronto"] = not falta
    out(r)
    return 0


def cmd_configurar(args):
    """A primeira vez num comando só: quem opera, a conta, as redes e as listas (a mesma planilha serve
    às duas redes; cada uma lê a sua coluna). Devolve um resumo curto; depois vêm o login e a voz."""
    redes = [r.strip().lower() for r in (args.redes or "").split(",") if r.strip()]
    if not redes or any(r not in R.REDES for r in redes):
        raise Erro("--redes é linkedin, x ou linkedin,x")
    erros, avisos, perfis = [], [], {}

    def passo(*argv, tolerar=None):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cod = main([str(a) for a in argv])
        try:
            dado = json.loads(buf.getvalue())
        except ValueError:
            dado = {}
        dado = dado if isinstance(dado, dict) else {}
        if cod and not (tolerar and tolerar in str(dado.get("erro"))):
            erros.append(f"{argv[0]}: {dado.get('erro') or buf.getvalue()[:200]}")
        return dado

    if args.operador or args.idioma:
        passo("operador", *(["--nome", args.operador] if args.operador else []),
              *(["--idioma", args.idioma] if args.idioma else []))
    conta = passo("conta", "--nome", args.nome).get("conta") or pasta_da(args.nome)
    for r in R.REDES:
        passo("conta", "--conta", conta, "--rede", r, "--ativa", "sim" if r in redes else "nao")
    for nome in args.nunca_citar or []:
        passo("conta", "--conta", conta, "--nunca-citar", nome)
    for nome in args.pode_citar or []:
        passo("conta", "--conta", conta, "--pode-citar", nome)
    for r, perfil in (("linkedin", args.perfil_linkedin), ("x", args.perfil_x)):
        if r in redes and perfil:
            if not chave_perfil(r, perfil):
                erros.append(f"perfil do {ROTULO[r]} não reconhecido: {perfil}")
                continue
            passo("conta", "--conta", conta, "--rede", r, "--perfil", perfil)
    if not (args.lista and RX_GOOGLE.search(args.lista)):
        # sem link do Google, a lista é o CSV local (vazio, ou com quem estava no Excel/CSV mandado)
        d = passo("lista", "--conta", conta, "--nome", "Principal", "--csv",
                  *(["--excel", args.lista] if args.lista else []))
        perfis = dict(d.get("perfis_ativos") or {})
        if "x" in redes and args.x_lista:
            passo("lista", "--conta", conta, "--rede", "x", "--nome", "Principal", "--x-lista", args.x_lista)
        elif "x" in redes and args.lista and not perfis.get("x"):
            passo("conta", "--conta", conta, "--rede", "x", "--ativa", "nao")
            avisos.append("o X ficou desligado: a lista não tem o @ ou o link do X de ninguém. Para "
                          "ligar, mande o link de uma Lista do X (https://x.com/i/lists/...) ou ponha os @")
        if not args.lista:
            avisos.append(f"a lista está vazia: {d.get('csv')} (ponha os perfis no Excel ou peça ao Claude)")
        redes_planilha = []
    else:
        redes_planilha = redes
    for r in redes_planilha:
        extra = []
        if args.lista:
            extra += ["--planilha" if RX_GOOGLE.search(args.lista) else "--excel", args.lista]
        if r == "x" and args.x_lista:
            extra += ["--x-lista", args.x_lista]
        if not extra:
            avisos.append(f"{ROTULO[r]}: falta a lista (o link da planilha do Google)")
            continue
        d = passo("lista", "--conta", conta, "--rede", r, "--nome", "Principal", *extra,
                  tolerar="não achei a coluna" if r == "x" else None)
        perfis[r] = d.get("perfis_ativos", 0)
        if r == "x" and not perfis[r] and not args.x_lista:
            passo("conta", "--conta", conta, "--rede", "x", "--ativa", "nao")
            avisos.append("o X ficou desligado: a planilha não tem o @ ou o link do X de ninguém. Para "
                          "ligar, mande o link de uma Lista do X (https://x.com/i/lists/...)")
    out({"conta": conta, "redes": redes, "perfis_por_rede": perfis, "erros": erros, "avisos": avisos,
         "proximo": "login (uma janela, uma aba por rede)"})
    return 2 if erros else 0


def cmd_operador(args):
    op = operador()
    if args.nome:
        op["nome"] = args.nome
    if args.idioma:
        op["idioma"] = args.idioma
    gravar_json(BASE / "operador.json", op)
    out(op)
    return 0


def cmd_conta(args):
    if args.nome:
        pasta = pasta_da(args.nome)
        if not arq(pasta, "conta.json").exists():
            gravar_conta(pasta, conta_nova(args.nome))
    else:
        pasta = resolver_conta(args.conta)
    c = ler_conta(pasta)
    avisos = []
    if args.nunca_citar and args.nunca_citar not in c.setdefault("nomes_que_nunca_cita", []):
        c["nomes_que_nunca_cita"].append(args.nunca_citar)
    if args.pode_citar:
        c["nomes_que_nunca_cita"] = [n for n in c.get("nomes_que_nunca_cita", [])
                                     if n.casefold() != args.pode_citar.casefold()]
    if args.ativa and not args.rede:
        # a conta inteira: desligada, o vigia passa por ela sem abrir nada (os dados ficam)
        c["ligada"] = args.ativa == "sim"
    if args.rede:
        cfg = c["redes"].setdefault(args.rede, conta_nova(c["nome"])["redes"][args.rede])
        if args.ativa:
            cfg["ativa"] = args.ativa == "sim"
        if args.modo and args.modo != cfg.get("modo"):
            if args.modo == "sozinho" and not R.propor_sozinho(eventos(pasta, args.rede)):
                raise Erro(f"o automático do {ROTULO[args.rede]} só liga depois de {R.REVISOES_PARA_SOZINHO} "
                           "rodadas revisadas seguidas sem correção (até 10% editados ou tirados). "
                           "Siga revisando: o /replai avisa quando der.")
            cfg["modo"] = args.modo
            registrar(pasta, args.rede, "modo", modo=args.modo)
        if args.perfil is not None:
            cfg["perfil"] = args.perfil
        for k, v in (("comentarios", args.teto_comentarios), ("curtidas", args.teto_curtidas)):
            if v is not None:
                maximo = R.TETO[args.rede][k][1]
                if v > maximo:
                    avisos.append(f"o máximo de {k} por dia é {maximo}; vale {maximo}")
                cfg.setdefault("teto", {})[k] = v
        if args.ignorar_proibida:
            cfg.setdefault("proibidas_ignorar", []).append(args.ignorar_proibida)
    gravar_conta(pasta, c)
    if args.ativa and not args.rede and any(rede_com_vigia(c, r) for r in R.REDES):
        acertar_tarefa_do_vigia()           # a única tarefa do PC só existe se alguma conta ligada a usa
    out(dict({"conta": pasta, "avisos": avisos}, **c))
    return 0


def conta_ligada(c):
    return c.get("ligada", True)


def rede_com_vigia(c, rede):
    cfg = (c.get("redes") or {}).get(rede) or {}
    return bool(cfg.get("ativa") and cfg.get("vigia"))


def cmd_liberar(args):
    """Quem opera solta a parada de hoje de uma rede (por exemplo, uma parada que não era bloqueio).
    Fica gravado no registro, nada é apagado; a parada continua contando para o corte de 7 dias.
    Sessão caída não se libera aqui: é o `login`."""
    pasta, c = carregar(args)
    evs = eventos(pasta, args.rede)
    if not R.situacao_paradas(evs, agora())[0]:
        out({"liberada": False, "motivo": "a rede não está parada hoje"})
        return 0
    registrar(pasta, args.rede, "liberada", motivo=args.motivo or "quem opera liberou")
    cot = R.cotas(args.rede, agora(), eventos(pasta, args.rede), rede_cfg(c, args.rede).get("teto"))
    out({"liberada": True, "cota_agora": cot})
    return 0


def cmd_contas(args):
    """Todas as contas deste PC numa olhada: ligada ou não, redes, modo, vigia, tamanho da lista e o que
    saiu hoje. É por aqui que quem opera escolhe quais contas rodam (`conta --conta X --ativa sim|nao`)."""
    saida = []
    for pasta in contas():
        try:
            c = ler_conta(pasta)
        except Erro as e:
            saida.append({"conta": pasta, "erro": str(e)})
            continue
        redes = {}
        for r, cfg in (c.get("redes") or {}).items():
            if not cfg.get("ativa"):
                continue
            try:
                n = len(perfis_da_rede(pasta, c, r))
            except Erro:
                n = None
            evs = eventos(pasta, r)
            redes[r] = {"modo": cfg.get("modo"), "vigia": bool(cfg.get("vigia")), "perfis": n,
                        "comentarios_hoje": R.contagens(evs, agora())["comentarios_dia"],
                        "parada": bool(R.situacao_paradas(evs, agora())[0])}
        saida.append({"conta": pasta, "nome": c.get("nome"), "ligada": conta_ligada(c), "redes": redes,
                      "lista": next((li["csv"] for li in c.get("listas") or [] if li.get("csv")), None)
                      or ("planilha do Google" if any(li.get("planilha") for li in c.get("listas") or []) else None)})
    out({"contas": saida, "vigia_do_pc": any(x.get("ligada") and any(v["vigia"] for v in x["redes"].values())
                                            for x in saida if "erro" not in x)})
    return 0


def migrar_para_csv(pasta, c, nome, caminho, origem=None):
    """Cria o CSV com quem já está nas listas `nome` (das duas redes) ou no arquivo/link `origem`, e
    aponta essas listas para ele. Um CSV que já existe não é sobrescrito: só passa a ser a fonte."""
    caminho = Path(caminho)
    alvo = R.sem_acento(nome).casefold()
    redes = [r for r in R.REDES if (c["redes"].get(r) or {}).get("ativa")] or list(R.REDES)
    criado = 0
    if not caminho.exists():
        por_rede = {}
        wb = abrir_planilha(pasta)
        for r in redes:
            if origem:
                try:
                    por_rede[r] = ler_tabela(origem, r)
                except Erro:
                    por_rede[r] = []        # a planilha não tem a coluna dessa rede
            else:
                por_rede[r] = [d for li in c.get("listas") or [] if li["rede"] == r
                               and R.sem_acento(li["nome"]).casefold() == alvo
                               for d in linhas_da_lista(pasta, li, wb)]
        linhas = LC.juntar(por_rede)
        try:
            LC.gravar(caminho, linhas)
        except LC.ArquivoAberto:
            raise Erro(f"o arquivo está aberto no Excel: feche {caminho.name} e rode de novo")
        criado = len(linhas)
    for r in redes:
        li = next((x for x in c.setdefault("listas", [])
                   if x["rede"] == r and R.sem_acento(x["nome"]).casefold() == alvo), None)
        if not li:
            li = {"nome": nome, "rede": r, "prioridade": "normal", "ativa": True}
            c["listas"].append(li)
        li["csv"] = str(caminho)
        li.pop("planilha", None)
    gravar_conta(pasta, c)
    return {"csv": str(caminho), "pessoas_trazidas": criado, "redes": redes}


def lista_csv_da_conta(pasta, c, nome=None):
    """(lista, caminho) do CSV da conta: o da lista `nome` ou o primeiro que houver."""
    alvo = R.sem_acento(nome).casefold() if nome else None
    for li in c.get("listas") or []:
        if li.get("csv") and (alvo is None or R.sem_acento(li["nome"]).casefold() == alvo):
            return li, Path(li["csv"])
    raise Erro("esta conta ainda não tem lista em CSV: rode 'lista --nome Principal --csv' (traz quem já está "
               "na lista de hoje para o arquivo)")


def cmd_perfil(args):
    """Mexe no CSV da conta: adicionar, tirar, pausar, retomar ou listar perfis. É assim que o Claude
    (Code ou app) edita a lista a pedido de quem opera; no Excel vale igual."""
    pasta, c = carregar(args)
    _li, caminho = lista_csv_da_conta(pasta, c, args.lista)
    linhas = LC.ler(caminho)
    res = {"csv": str(caminho)}
    try:
        if args.adicionar:
            linhas, res["feito"] = LC.adicionar(linhas, args.adicionar, nome=args.nome or "",
                                                prioridade=args.prioridade or "", obs=args.obs or "")
            res["pessoa"] = linhas[LC.achar(linhas, args.adicionar[0])]
        elif args.tirar:
            linhas, res["pessoa"] = LC.tirar(linhas, args.tirar)
            res["feito"] = "tirada"
        elif args.pausar or args.retomar:
            linhas, res["pessoa"] = LC.incluir(linhas, args.pausar or args.retomar, bool(args.retomar))
            res["feito"] = "retomada" if args.retomar else "pausada"
    except ValueError as e:
        raise Erro(str(e))
    except LookupError as e:
        raise Erro(f"não achei '{e.args[0]}' na lista (mande o link do perfil ou o @; um nome repetido "
                   "não basta)")
    if res.get("feito"):
        try:
            LC.gravar(caminho, linhas)
        except LC.ArquivoAberto:
            raise Erro(f"a lista está aberta no Excel: feche {caminho.name} e peça de novo")
    ativos = [ln for ln in linhas if LC.ativa(ln)]
    res["total"] = len(linhas)
    res["ativos"] = {"linkedin": sum(1 for ln in ativos if ln.get("LinkedIn")),
                     "x": sum(1 for ln in ativos if ln.get("X"))}
    if args.listar:
        busca = R.sem_acento(args.listar if isinstance(args.listar, str) else "").casefold()
        res["pessoas"] = [ln for ln in linhas if not busca or busca in R.sem_acento(
            " ".join(ln.get(k, "") for k in ("Nome", "LinkedIn", "X", "Observação"))).casefold()]
    out(res)
    return 0


def cmd_lista(args):
    pasta, c = carregar(args)
    if args.csv is not None:
        origem = args.excel or args.planilha
        caminho = Path(args.csv) if args.csv else arq(pasta, "lista.csv")
        res = migrar_para_csv(pasta, c, args.nome, caminho, origem=origem)
        c = ler_conta(pasta)
        res["perfis_ativos"] = {r: len(perfis_da_rede(pasta, c, r, args.nome)) for r in res["redes"]}
        out(res)
        return 0
    if not args.rede:
        raise Erro("diga a rede: --rede linkedin ou --rede x (ou use --csv, que serve às duas)")
    alvo = R.sem_acento(args.nome).casefold()
    li = next((x for x in c.setdefault("listas", [])
               if x["rede"] == args.rede and R.sem_acento(x["nome"]).casefold() == alvo), None)
    if not li:
        li = {"nome": args.nome, "rede": args.rede, "prioridade": "normal", "ativa": True}
        c["listas"].append(li)
    if args.prioridade:
        li["prioridade"] = args.prioridade
    if args.ativa:
        li["ativa"] = args.ativa == "sim"
    if args.x_lista:
        if args.rede != "x" or not re.search(r"(x|twitter)\.com/i/lists/\d+", args.x_lista):
            raise Erro("a Lista do X é um link como https://x.com/i/lists/123456 (e só vale para --rede x)")
        li["x_lista"] = args.x_lista.split("?")[0].rstrip("/")
    gravar_conta(pasta, c)
    res = {"lista": li, "aba": aba_da_lista(args.rede, li["nome"])}
    if args.planilha or (args.excel and RX_GOOGLE.search(args.excel)):
        url = args.planilha or args.excel
        if not RX_GOOGLE.search(url):
            raise Erro("o link da planilha do Google é como https://docs.google.com/spreadsheets/d/...")
        res["linhas_na_planilha"] = len(linhas_do_google(pasta, url, args.rede, forcar=True))
        li["planilha"] = url
        gravar_conta(pasta, c)
        res["lista"] = li
    elif args.excel:
        n, ja = importar_lista(pasta, args.rede, li["nome"], args.excel)
        res.update(importados=n, ja_estavam_ou_sem_perfil=ja)
    else:
        wb = abrir_planilha(pasta)
        if res["aba"] not in wb.sheetnames:
            _cabecalho(wb.create_sheet(res["aba"]), TXT[idioma()]["lista"])
            salvar_planilha(wb, pasta)
    res["perfis_ativos"] = len(perfis_da_rede(pasta, c, args.rede, li["nome"]))
    out(res)
    return 0


def cmd_status(args):
    pasta, c = carregar(args)
    res = {"conta": pasta, "nome": c["nome"], "redes": {}}
    for rede, cfg in c["redes"].items():
        if cfg.get("ativa"):
            res["redes"][rede] = status_da_rede(pasta, c, rede)
    res["planilha"] = str(planilha_de(pasta))
    res["planilha_atualizada"] = sincronizar_planilha(pasta, c)
    out(res)
    return 0


# --------------------------------------------------------------------------------------------
# Coletar (LinkedIn)
# --------------------------------------------------------------------------------------------
def conferir_conta(pasta, c, rede, vanity_logada):
    """A conta logada no navegador é a da conta? Na primeira vez aprende o perfil pelo /me."""
    cfg = c["redes"][rede]
    esperado = chave_perfil(rede, cfg.get("perfil") or "")
    logada = (vanity_logada or "").lower()
    if esperado and esperado != logada:
        raise Erro(f"o {rede} logado é '{vanity_logada}', mas a conta {c['nome']} é '{esperado}'. "
                   "Refaça o login com a conta certa.", 4)
    if not esperado and logada:
        cfg["perfil"] = (f"https://www.linkedin.com/in/{logada}/" if rede == "linkedin"
                         else f"https://x.com/{logada}")
        gravar_conta(pasta, c)
        return True                    # aprendeu agora: quem opera confirma (o testar avisa)
    return False


def vencer(pasta, rede):
    for pid in R.a_vencer(R.estados(eventos(pasta, rede)), rede, agora()):
        registrar(pasta, rede, "vencido", id=pid)


def post_do_linkedin(p, pf):
    texto = p.get("texto") or ""
    return {"id": str(p["activity_id"]), "canon": str(p.get("original_id") or p["activity_id"]),
            "rede": "linkedin", "autor": (p.get("autor_vanity") or pf["chave"]).lower(),
            "nome": p.get("autor") or pf["nome"], "headline": (p.get("autor_headline") or "")[:120],
            "texto": texto, "data": p.get("data"), "n_curtidas": p.get("n_curtidas"),
            "n_comentarios": p.get("n_comentarios"), "repost_puro": bool(p.get("repost_puro")),
            "url": p["url"], "fonte": f"lista:{pf['lista']}", "prioridade": pf["prioridade"],
            "idioma": R.idioma(texto)}


def coletar_linkedin(pasta, c, perfis, cota, voy, simular=False, vigia=False, so_posts=None):
    """Lê os perfis (orçamento de leitura), escolhe pela regra, confere se a conta já comentou e
    grava o pool. Em simulação nada vai para o registro (só as leituras, que aconteceram).
    `so_posts` (vigia): [(vanity, activity)] das notificações; só esses autores são lidos e só esses
    posts entram. `vigia`: post velho fica fora e o que está no atraso sorteado espera a próxima."""
    import linkedin as L
    rede = "linkedin"
    try:
        me = voy.me()
    except L.VoyagerErro as e:
        raise Erro(f"não consegui ler a conta logada: {e}", 2)
    conferir_conta(pasta, c, rede, me.get("vanity"))
    t = agora()
    evs = eventos(pasta, rede)
    reg = R.estados(evs)
    lim = R.LEITURA[rede]
    orcamento = min(lim["rodada"], lim["dia"] - R.contagens(evs, t)["leituras_dia"]) - lim["reserva"]
    if orcamento <= 0:
        return {"nada_a_fazer": "teto de leituras do dia atingido"}
    descanso = R.autores_em_descanso(reg, rede, t)
    lido_em = {e.get("autor"): e.get("quando", "") for e in evs if e.get("ev") == "lido"}
    ordem = sorted((p for p in perfis if p["chave"] not in descanso),
                   key=lambda p: (0 if p["prioridade"] == "alta" else 1, lido_em.get(p["chave"], "")))
    ids_avisados = None
    if so_posts is not None:
        avisados = {v for v, _a in so_posts}
        ids_avisados = {str(a) for _v, a in so_posts}
        ordem = [p for p in ordem if p["chave"] in avisados]
    cache = ler_json(arq(pasta, "cache-linkedin.json"), {}) or {}
    posts, lidos, perfis_lidos, erros, finais, adiados, de_outros = [], 0, 0, [], [], 0, 0
    try:
        for pf in ordem:
            if lidos + (0 if pf["chave"] in cache else 1) + 1 > orcamento:
                break
            try:
                urn = cache.get(pf["chave"])
                if not urn:
                    urn = voy.urn_do_perfil(pf["chave"])
                    lidos += 1
                    cache[pf["chave"]] = urn
                brutos = voy.posts(urn, count=10)
                lidos += 1
            except L.VoyagerErro as e:
                if e.tipo in (L.ERRO_BLOQUEIO, L.ERRO_SESSAO):
                    raise
                erros.append(f"{pf['nome']}: {e}")
                continue
            perfis_lidos += 1
            registrar(pasta, rede, "lido", autor=pf["chave"])
            # a atividade do perfil traz post de outras pessoas (o que ele repostou com texto, curtiu,
            # comentou): só entra o que a própria pessoa da lista escreveu
            proprios = [p for p in brutos if (p.get("autor_vanity") or pf["chave"]).strip("/").lower() == pf["chave"]]
            de_outros += len(brutos) - len(proprios)
            posts.extend(post_do_linkedin(p, pf) for p in proprios
                         if ids_avisados is None or str(p["activity_id"]) in ids_avisados)
        if vigia:
            posts = [p for p in posts if R.situacao_no_vigia(p, rede, t) != "velho"]
        escolhidos, fora = R.selecionar(posts, rede, t, reg, cota)
        for p in escolhidos:
            if vigia and R.situacao_no_vigia(p, rede, t) == "cedo":
                adiados += 1                  # sem registrar: a próxima execução pega
                continue
            if p.get("n_comentarios") != 0:
                try:
                    if voy.comentario_da_conta(p["id"], me):
                        if not simular:
                            registrar(pasta, rede, "ja_comentado", id=p["id"], canon=p["canon"],
                                      autor=p["autor"], motivo="a conta já tinha comentado (coleta)")
                        continue
                except L.VoyagerErro as e:
                    if e.tipo in (L.ERRO_BLOQUEIO, L.ERRO_SESSAO):
                        raise
            finais.append(p)
    except L.VoyagerErro as e:
        gravar_json(arq(pasta, "cache-linkedin.json"), cache)
        # 403 em sequência: em 12/11/2026 era o LinkedIn derrubando a sessão (o cookie li_at sumiu e
        # tudo virou 401). Confere a sessão antes de concluir qualquer coisa.
        if e.tipo == L.ERRO_SESSAO or (e.status == 403 and L.sessao_expirada(getattr(voy, "page", None))):
            marcar_sessao(pasta, rede, False)
            raise ErroSessao(f"a sessão do LinkedIn caiu: rode o login ({e})")
        if e.status == 403:
            ate = agora() + timedelta(minutes=R.PAUSA_LEITURA_MIN)
            registrar(pasta, rede, "pausa_leitura", ate=ate.isoformat(), motivo=f"leitura: {e}")
            raise Erro(f"LEITURA EM PAUSA: o LinkedIn recusou leituras seguidas ({e}), com a sessão ok. "
                       f"Volta sozinho às {ate:%H:%M}.", 4)
        registrar(pasta, rede, "parada", motivo=f"leitura: {e}")
        raise Erro(f"RODADA PARADA: o LinkedIn deu sinal de bloqueio na leitura ({e}). "
                   "A rede fica parada até amanhã.", 4)
    gravar_json(arq(pasta, "cache-linkedin.json"), cache)
    return {"simulacao": bool(simular), "perfis_lidos": perfis_lidos, "leituras": voy.feitas,
            "posts_vistos": len(posts), "candidatos": len(finais), "cota_comentarios": cota,
            "fora": _fechar_coleta(pasta, rede, reg, finais, fora, cota, simular), "erros": erros[:10],
            "de_outras_pessoas": de_outros,
            **({"no_atraso": adiados, "avisos": len(so_posts or [])} if vigia else {})}


def _fechar_coleta(pasta, rede, reg, finais, fora, cota, simular):
    """O fim de toda coleta: grava o pool (o real acumula os que ainda esperam texto; a simulação
    fica à parte), registra a seleção, aponta a rodada atual e zera as tentativas. Devolve a
    contagem dos motivos de quem ficou fora."""
    rd = rodada_dir(pasta, rede)
    if simular:
        gravar_json(pool(pasta, rede, True), {"quando": agora_iso(), "cota": cota, "posts": finais})
    else:
        antigos = [p for p in ((ler_json(pool(pasta, rede, False), {}) or {}).get("posts") or [])
                   if (reg.get(p["id"]) or {}).get("estado") == "selecionado"]
        for p in finais:
            registrar(pasta, rede, "selecionado", id=p["id"], canon=p["canon"], autor=p["autor"],
                      nome=p["nome"], url=p["url"], data=p["data"], trecho=p["texto"][:120],
                      fonte=p["fonte"], n_comentarios=p.get("n_comentarios"))
        gravar_json(pool(pasta, rede, False), {"quando": agora_iso(), "cota": cota, "posts": antigos + finais})
    gravar_json(rd / "atual.json", {"simular": bool(simular)})
    for nome in ("textos.json", "tentativas.json", "reprovados.json"):
        try:
            (rd / nome).unlink()
        except OSError:
            pass
    motivos = {}
    for _p, m in fora:
        motivos[m] = motivos.get(m, 0) + 1
    return motivos


def _leitor_linkedin(pasta, page):
    import linkedin as L
    if L.sessao_expirada(page):
        raise ErroSessao("o LinkedIn não está logado nesta sessão: rode 'login'")
    return L.Voyager(page, pausa_seg=R.LEITURA["linkedin"]["pausa"],
                     ao_ler=lambda tipo: registrar(pasta, "linkedin", "leitura", tipo=tipo))


def abrir_redes(pasta, c, pw, redes, fora_da_tela=True):
    """Um navegador, uma janela e UMA aba, que as redes revezam (cada post abre o próprio link antes
    de agir): aba em segundo plano não anima, e o clique do Playwright esperava o botão "parar de se
    mexer" até estourar. Sempre escondido depois do login, no Windows e no Mac (REPLAI_VISIVEL=1
    mostra, para investigar). (ctx, {rede: (page, leitor)}, {rede: Erro}). A rede que não abriu
    (sessão caída) não impede a outra. Quem chama fecha o ctx."""
    import linkedin as L
    fora_da_tela = fora_da_tela and not os.environ.get("REPLAI_VISIVEL")
    try:
        ctx = L.abrir_contexto(pw, sessao_de(pasta, c, redes[0]), fora_da_tela=fora_da_tela)
    except L.ErroNavegador as e:
        raise Erro(str(e), 2)
    abertas, erros = {}, {}
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    for rede in redes:
        try:
            abertas[rede] = (page, (_leitor_x if rede == "x" else _leitor_linkedin)(pasta, page))
            marcar_sessao(pasta, rede, True)
        except ErroSessao as e:
            marcar_sessao(pasta, rede, False)
            erros[rede] = e
        except Erro as e:
            erros[rede] = e
    return ctx, abertas, erros


def abrir_rede(pasta, c, pw, rede, fora_da_tela=True):
    """(ctx, page, leitor) de uma rede só; sessão caída fecha o navegador e vira Erro."""
    ctx, abertas, erros = abrir_redes(pasta, c, pw, [rede], fora_da_tela)
    if erros:
        fechar(ctx)
        raise erros[rede]
    return (ctx, *abertas[rede])


# --------------------------------------------------------------------------------------------
# Coletar (X): a Lista nativa e a busca pelos @ do Excel, uma página para muitos perfis
# --------------------------------------------------------------------------------------------
IDIOMAS_X_SEM = ("und", "zxx", "qme", "qht", "qam", "qst", "art")


def post_do_x(t, lista, prioridade):
    idioma = "" if (t.get("idioma") or "") in IDIOMAS_X_SEM else (t.get("idioma") or "")
    return {"id": t["id"], "canon": t.get("retweet_de") or t.get("citacao_de") or t["id"], "rede": "x",
            "autor": t["autor"], "nome": t.get("nome") or t["autor"], "headline": t.get("bio") or "",
            "texto": t.get("texto") or "", "data": t.get("data"), "n_curtidas": t.get("n_curtidas"),
            "n_comentarios": t.get("n_comentarios"), "repost_puro": bool(t.get("retweet_de")),
            "resposta": bool(t.get("resposta_a")), "url": t["url"], "fonte": f"lista:{lista}",
            "prioridade": prioridade, "idioma": idioma}


def fontes_x(pasta, c, so_lista=None):
    """[{tipo: 'lista', url, lista, prioridade}] para as Listas nativas e [{tipo: 'busca', handles,
    lista, prioridade}] para os @ das abas (lotes de até 15 por busca)."""
    import x as X
    fontes = []
    for li in c.get("listas") or []:
        if li["rede"] != "x" or not li.get("ativa", True):
            continue
        if so_lista and R.sem_acento(li["nome"]).casefold() != R.sem_acento(so_lista).casefold():
            continue
        pri = li.get("prioridade") or "normal"
        if li.get("x_lista"):
            fontes.append({"tipo": "lista", "url": li["x_lista"], "lista": li["nome"], "prioridade": pri})
        handles = [p["chave"] for p in perfis_da_rede(pasta, c, "x", li["nome"])]
        for i in range(0, len(handles), X.BUSCA_MAX_HANDLES):
            fontes.append({"tipo": "busca", "handles": handles[i:i + X.BUSCA_MAX_HANDLES],
                           "lista": li["nome"], "prioridade": pri})
    return fontes


def coletar_x(pasta, c, cota, leitor, simular=False, so_lista=None, vigia=False):
    """Lê as Listas e as buscas (orçamento de páginas), escolhe pela regra, confere nas respostas da
    conta se ela já respondeu e grava o pool. `vigia`: só posts com até 2h, e o que ainda está no
    atraso sorteado fica para a próxima execução (sem registrar nada)."""
    import x as X
    rede = "x"
    try:
        meu = leitor.me()
    except X.ErroX as e:
        raise erro_x(pasta, e, "o X não abriu")
    if not meu:
        raise Erro("não consegui ler a conta logada no X: rode 'login'", 2)
    conferir_conta(pasta, c, rede, meu)
    t = agora()
    evs = eventos(pasta, rede)
    reg = R.estados(evs)
    lim = R.LEITURA[rede]
    orcamento = min(lim["rodada"], lim["dia"] - R.contagens(evs, t)["leituras_dia"]) - lim["reserva"]
    if orcamento <= 0:
        return {"nada_a_fazer": "teto de leituras do dia atingido"}
    fontes = fontes_x(pasta, c, so_lista)
    if not fontes:
        raise Erro("nenhuma Lista do X nem @ nas listas ativas (use: lista --rede x --x-lista URL ou --excel)")
    cache = ler_json(arq(pasta, "cache-x.json"), {}) or {}
    membros, achados = {}, []
    try:
        for f in fontes:
            if leitor.feitas >= orcamento:
                break
            if f["tipo"] == "lista":
                mem = cache.get(f["url"]) or {}
                if not mem.get("handles") or mem.get("quando", "") < (t - timedelta(hours=24)).isoformat():
                    mem = {"quando": agora_iso(), "handles": leitor.membros(f["url"])}
                    cache[f["url"]] = mem
                tweets = leitor.lista(f["url"])
                for h in mem["handles"] or sorted(X.autores_de_topo(tweets)):
                    membros.setdefault(h, (f["lista"], f["prioridade"]))
            else:
                tweets = leitor.busca(f["handles"])
                for h in f["handles"]:
                    membros.setdefault(h, (f["lista"], f["prioridade"]))
            achados += tweets
        posts = [post_do_x(tw, *membros[tw["autor"]]) for tw in achados if tw["autor"] in membros]
        if vigia:
            posts = [p for p in posts if R.situacao_no_vigia(p, rede, t) != "velho"]
        escolhidos, fora = R.selecionar(posts, rede, t, reg, cota)
        respondidos = X.respondidos(leitor.respostas_da_conta(meu), meu) if escolhidos else {}
    except X.ErroX as e:
        gravar_json(arq(pasta, "cache-x.json"), cache)
        if e.tipo == "SESSAO":
            marcar_sessao(pasta, rede, False)
            raise ErroSessao("o X não está logado nesta sessão: rode 'login'")
        if e.tipo == "LEITURA":
            raise Erro(f"RODADA PARADA: {e}", 4)
        registrar(pasta, rede, "parada", motivo=f"leitura: {e}")
        raise Erro(f"RODADA PARADA: o X deu sinal de bloqueio na leitura ({e}). A rede fica parada até amanhã.", 4)
    gravar_json(arq(pasta, "cache-x.json"), cache)
    finais, adiados = [], 0
    for p in escolhidos:
        if p["id"] in respondidos or p["canon"] in respondidos:
            if not simular:
                registrar(pasta, rede, "ja_comentado", id=p["id"], canon=p["canon"], autor=p["autor"],
                          comentou_em=respondidos.get(p["id"]) or respondidos.get(p["canon"]),
                          motivo="a conta já tinha respondido (coleta)")
            continue
        if vigia and R.situacao_no_vigia(p, rede, t) == "cedo":
            adiados += 1                      # sem registrar: a próxima execução pega
            continue
        finais.append(p)
    res = {"simulacao": bool(simular), "paginas": leitor.feitas, "posts_vistos": len(posts),
           "candidatos": len(finais), "cota_comentarios": cota,
           "fora": _fechar_coleta(pasta, rede, reg, finais, fora, cota, simular)}
    if vigia:
        res["no_atraso"] = adiados
    return res


def _leitor_x(pasta, page):
    import x as X
    if X.sessao_expirada(page):
        raise ErroSessao("o X não está logado nesta sessão: rode 'login'")
    return X.Leitor(page, pausa=R.LEITURA["x"]["pausa"],
                    ao_ler=lambda tipo: registrar(pasta, "x", "leitura", tipo=tipo))


def cota_da_coleta(pasta, c, rede, simular=False, maximo=None):
    """(cota de comentários desta rodada, motivo quando zero)."""
    vencer(pasta, rede)
    cot = R.cotas(rede, agora(), eventos(pasta, rede), rede_cfg(c, rede).get("teto"))
    cota = cot["comentarios"]
    if simular and cota <= 0:
        cota = R.POR_RODADA[rede]
    if maximo:
        cota = min(cota, maximo)
    return cota, cot["motivo"]


def coletar_rede(pasta, c, rede, cota, leitor, simular=False, lista=None):
    if rede == "x":
        return coletar_x(pasta, c, cota, leitor, simular=simular, so_lista=lista)
    perfis = perfis_da_rede(pasta, c, rede, lista)
    if not perfis:
        raise Erro("nenhum perfil nas listas ativas do LinkedIn (use: lista --rede linkedin ...)")
    return coletar_linkedin(pasta, c, perfis, cota, leitor, simular=simular)


def cmd_coletar(args):
    """Sem --rede, as redes ligadas, no mesmo navegador (uma aba por rede)."""
    pasta, c = carregar(args)
    res, cotas = {}, {}
    for rede in redes_pedidas(c, args.rede):
        cota, motivo = cota_da_coleta(pasta, c, rede, args.simular, args.max)
        if cota <= 0:
            res[rede] = {"nada_a_fazer": motivo}
            continue
        try:
            perfis_da_rede(pasta, c, rede, args.lista)     # lista quebrada: avisa sem abrir o navegador
        except Erro as e:
            res[rede] = erro_dict(e)
            continue
        cotas[rede] = cota
    if cotas:
        from playwright.sync_api import sync_playwright
        with Trava(trava_de(pasta, c, next(iter(cotas)))), sync_playwright() as pw:
            ctx, abertas, erros = abrir_redes(pasta, c, pw, list(cotas))
            try:
                res.update({r: erro_dict(e) for r, e in erros.items()})
                for rede, (_page, leitor) in abertas.items():
                    try:
                        res[rede] = coletar_rede(pasta, c, rede, cotas[rede], leitor, args.simular, args.lista)
                    except Erro as e:
                        res[rede] = erro_dict(e)
            finally:
                fechar(ctx)
    return saida_redes(args.rede, res)


URL_LOGIN = {"linkedin": ("LinkedIn", "https://www.linkedin.com/login"),
             "x": ("X", "https://x.com/i/flow/login")}


def caminho_chrome():
    import linkedin as L
    return L.navegador_do_pc()


MAC = sys.platform == "darwin"
LOGIN_COOKIE = {"linkedin": ("linkedin.com", "li_at"), "x": ("x.com", "auth_token")}
LOGIN_MAX_SEG = 20 * 60


def logou_desde(perfil, redes, desde):
    """As redes que gravaram o cookie de login na pasta da sessão depois de `desde` (epoch). Lê só o nome
    e a hora (o valor é criptografado), numa cópia: o Chrome segura o arquivo e grava a cada 30 s."""
    import shutil
    import sqlite3
    import tempfile
    marca = int((desde + 11644473600) * 1_000_000)          # o Chrome conta microssegundos desde 1601
    for banco in (Path(perfil) / "Default" / "Network" / "Cookies", Path(perfil) / "Default" / "Cookies"):
        if not banco.exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            try:
                for sufixo in ("", "-wal", "-journal"):
                    if Path(f"{banco}{sufixo}").exists():
                        shutil.copyfile(f"{banco}{sufixo}", Path(tmp) / f"Cookies{sufixo}")
                with contextlib.closing(sqlite3.connect(Path(tmp) / "Cookies")) as db:
                    linhas = db.execute("SELECT host_key, name FROM cookies WHERE creation_utc > ?",
                                        (marca,)).fetchall()
            except (OSError, sqlite3.Error):                 # cópia no meio de uma gravação: tenta de novo
                return set()
        return {r for r in redes
                if any(h.endswith(LOGIN_COOKIE[r][0]) and n == LOGIN_COOKIE[r][1] for h, n in linhas)}
    return set()


def fechar_janela(proc, mac=MAC):
    """Fecha o Chrome do login como quem fecha a janela, para ele gravar os cookies: no Mac, SIGTERM
    (o Cmd+Q); no Windows, taskkill sem /f (manda o "fechar" à janela, não mata)."""
    import subprocess
    if mac or os.name != "nt":
        proc.terminate()
    else:
        subprocess.run(["taskkill", "/pid", str(proc.pid)], capture_output=True)


def fechar_janela_do_perfil(perfil, mac=MAC):
    """Fecha com delicadeza (para gravar os cookies) o Chrome do login aberto nesta pasta — o aberto SEM
    a porta, que o auto-detector não enxerga no Windows (lá o arquivo de cookies fica travado pelo Chrome,
    não dá para ler quem logou). É o que a skill roda (`login --fechar`) quando quem opera diz que entrou.
    Mac: SIGTERM, como no login. Windows: taskkill sem /f (manda a janela fechar) no chrome.exe-pai cujo
    --user-data-dir é esta pasta, sem os processos-filho (gpu, renderer...). True se fechou algum."""
    import linkedin as L
    import subprocess
    if mac or os.name != "nt":
        return L.soltar_perfil(perfil)
    alvo = str(Path(perfil)).replace("/", "\\").lower()
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
          "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
    try:
        dados = json.loads(r.stdout or "[]")
    except ValueError:
        return False
    if isinstance(dados, dict):
        dados = [dados]
    fechou = False
    for p in dados:
        cmd = (p.get("CommandLine") or "").lower()
        if alvo in cmd and "--type=" not in cmd:
            subprocess.run(["taskkill", "/pid", str(p["ProcessId"])], capture_output=True)
            fechou = True
    return fechou


def esperar_login(proc, perfil, redes, mac=MAC, pausa=5, limite=LOGIN_MAX_SEG, fechar=None):
    """Espera quem opera terminar o login e fecha a janela assim que todas as redes pedidas gravarem um
    cookie de login novo (a pessoa só entra na conta; não precisa fechar nada). No Windows o arquivo de
    cookies fica travado pelo Chrome e o auto-detector não enxerga o login: lá quem fecha a janela é a
    skill (`login --fechar`) quando a pessoa avisa, ou a própria pessoa — aí `proc.poll()` muda e isto
    segue. Em 20 minutos, fecha de qualquer jeito."""
    import subprocess
    fechar = fechar or (lambda p: fechar_janela(p, mac))
    inicio = time.time()
    while proc.poll() is None:
        if time.time() - inicio > limite or logou_desde(perfil, redes, inicio) == set(redes):
            fechar(proc)
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
            break
        time.sleep(pausa)


def cmd_login(args):
    """O Chrome do Replai numa janela comum, uma aba por rede, sem a porta do robô: com ela o Chrome
    se declara automatizado (navigator.webdriver) e o Google recusa o login. Ao fechar, o robô
    confere cada rede no mesmo Chrome, agora com a porta."""
    import linkedin as L
    from playwright.sync_api import sync_playwright
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    perfil = sessao_de(pasta, c, redes[0])
    if getattr(args, "fechar", False):     # a skill fecha a janela quando quem opera avisa que logou
        out({"fechou": fechar_janela_do_perfil(perfil)})
        return 0
    nomes = " e no ".join(URL_LOGIN[r][0] for r in redes)
    out(f"Abrindo o navegador do Replai, uma aba por rede. Entre no {nomes} com a conta: a janela fecha "
        "sozinha quando terminar.")
    with Trava(trava_de(pasta, c, redes[0])), sync_playwright() as pw:
        L.fechar_aberto(pw, perfil)        # um do robô que ficou aberto (talvez escondido) engoliria a janela
        try:
            _porta, proc = L.abrir_chrome(perfil, [URL_LOGIN[r][1] for r in redes], porta=False,
                                          exe=caminho_chrome() or pw.chromium.executable_path)
        except L.ErroNavegador as e:
            raise Erro(str(e), 2)
        esperar_login(proc, perfil, redes)
        ctx, abertas, erros = abrir_redes(pasta, c, pw, redes, fora_da_tela=True)
        fechar(ctx)
    res = {r: "logado" for r in abertas}
    res.update({r: "NÃO logado: rode o login de novo e entre nessa aba" for r in erros})
    out(res)
    return 2 if any(r not in abertas for r in redes) else 0


# --------------------------------------------------------------------------------------------
# Escrita: o pacote do escritor e a validação do que ele entregou
# --------------------------------------------------------------------------------------------
def secoes_doutrina(nomes):
    texto = (REFS / "doutrina.md").read_text(encoding="utf-8")
    escolhidas = []
    for parte in re.split(r"(?m)^## ", texto)[1:]:
        if parte.split("\n", 1)[0].strip().lower() in nomes:
            escolhidas.append("## " + parte.strip())
    return "\n\n".join(escolhidas)


def pendentes(simular, dados, reg, textos_sim):
    posts = (dados or {}).get("posts") or []
    if simular:
        return [p for p in posts if p["id"] not in textos_sim]
    return [p for p in posts if (reg.get(p["id"]) or {}).get("estado") == "selecionado"]


def pular(pasta, rede, pid, motivo, simular, textos_sim):
    if simular:
        textos_sim[pid] = {"pular": motivo}
    else:
        registrar(pasta, rede, "pulado", id=pid, motivo=motivo)


def pendentes_da_rodada(pasta, rede):
    """(simular, posts que esperam texto) da rodada atual."""
    simular, dados = rodada_atual(pasta, rede)
    if not dados:
        raise Erro("não há rodada coletada nesta rede (rode coletar antes)")
    textos_sim = ler_json(rodada_dir(pasta, rede) / "textos.json", {}) or {}
    return simular, pendentes(simular, dados, R.estados(eventos(pasta, rede)), textos_sim)


def cmd_lote(args):
    """Sem --rede, um pacote só para as redes que têm post esperando texto (um escritor, uma vez)."""
    pasta, c = carregar(args)
    pends, simular = {}, False
    for rede in redes_pedidas(c, args.rede):
        try:
            sim, pend = pendentes_da_rodada(pasta, rede)
        except Erro:
            if args.rede:
                raise
            continue
        if pend:
            pends[rede], simular = pend, simular or sim
    if not pends:
        out("Nada para escrever: todos os posts desta rodada já têm texto ou foram pulados.")
        return 0
    so = next(iter(pends)) if len(pends) == 1 else None
    saida = (rodada_dir(pasta, so) if so else arq(pasta, "rodada")) / "saida.json"
    out(montar_pacote(pasta, c, pends, simular,
                      "## Como entregar\n\n"
                      f"Grave com a ferramenta Write o arquivo:\n{saida}\n"
                      'no formato {"<id>": "comentário"} para comentar ou {"<id>": "-motivo curto"} para pular. '
                      "Responda todos os ids. Depois rode:\n"
                      f'<python> "{SCRIPT}" escrever --conta {pasta}' + (f" --rede {so}" if so else "")
                      + f' --arquivo "{saida}"'))
    return 0


ENTREGA_SO_JSON = ("## Como responder\n\nResponda SÓ com um objeto JSON, sem nada antes nem depois: "
                   '{"<id>": "comentário"} para comentar ou {"<id>": "-motivo curto"} para pular. '
                   "Responda todos os ids.")


def montar_pacote(pasta, c, pends, simular, entrega):
    """O texto que o escritor recebe, para uma rede ou as duas numa chamada só. `pends`: {rede: posts}.
    A doutrina comum e os nomes que a conta nunca cita vão uma vez; por rede, a doutrina da rede, a voz,
    as palavras proibidas, as aberturas recentes, os reprovados da tentativa anterior e os posts
    compactados. Com as duas redes, o id de cada post vem como "<rede>:<id>". `entrega` fecha o pacote."""
    redes = [r for r in R.REDES if pends.get(r)]
    varias = len(redes) > 1
    t = agora()
    total = sum(len(pends[r]) for r in redes)
    partes = [f"# Lote do Replai · {c['nome']} · {' + '.join(ROTULO[r] for r in redes)} · {total} posts"
              + (" · SIMULAÇÃO" if simular else ""),
              "Escreva um comentário por post ou pule. A doutrina diz o que é bom; a voz da rede manda no tom.",
              secoes_doutrina(("comum",)),
              "## Nomes que esta conta nunca cita\n\n" + (", ".join(nomes_da_conta(c)) or "nenhum")]
    for rede in redes:
        evs = eventos(pasta, rede)
        voz = voz_atual(pasta, rede)
        rascunho = arq(pasta, f"rascunho-voz-{rede}.md")
        if not voz and simular and rascunho.exists():
            voz = rascunho.read_text(encoding="utf-8")       # teste da voz antes de gravá-la
        if not voz:
            raise Erro(f"a conta ainda não tem voz para {rede}: crie com o roteiro de voz antes de escrever")
        pre = f"{rede}:" if varias else ""
        compactos = [{"id": pre + p["id"], "autor": f"{p['nome']} · {p.get('headline') or ''}".strip(" ·"),
                      "idioma": p.get("idioma") or "", "idade": idade_txt(p.get("data"), t),
                      "texto": limpar_texto(p["texto"], 700)} for p in pends[rede]]
        proib = proibidas(c, rede, evs)
        ab = R.aberturas_recentes(R.estados(evs))
        reprov = ler_json(rodada_dir(pasta, rede) / "reprovados.json", {}) or {}
        if varias:
            partes.append(f"# {ROTULO[rede]} (ids \"{rede}:...\")")
        partes += [secoes_doutrina((rede,)),
                   f"## Voz da conta no {ROTULO[rede]} (versão {versao_voz(pasta, rede)})\n\n{voz.strip()}",
                   f"## Palavras proibidas no {ROTULO[rede]}\n\n" + (", ".join(proib) if proib else "nenhuma"),
                   "## Aberturas recentes (não comece igual)\n\n" + ("\n".join(f"- {a}" for a in ab) if ab else "nenhuma")]
        if reprov:
            partes.append("## Reprovados na tentativa anterior (reescreva corrigindo)\n\n"
                          + "\n".join(f"- {pre}{k}: {'; '.join(v)}" for k, v in reprov.items()))
        partes.append(f"## Posts do {ROTULO[rede]}\n\n```json\n" + json.dumps(compactos, ensure_ascii=False, indent=1)
                      + "\n```")
    partes.append(entrega)
    return "\n\n".join(partes)


def separar_resposta(resp, redes):
    """{rede: {id: texto}} da resposta do escritor (com uma rede só, os ids vêm sem prefixo)."""
    if len(redes) == 1:
        return {redes[0]: resp}
    por = {r: {} for r in redes}
    for k, v in resp.items():
        rede, _, pid = str(k).partition(":")
        if rede in por:
            por[rede][pid] = v
    return por


def escrever_redes(pasta, c, redes, escritor):
    """O escritor (pacote -> {id: texto}) escreve as redes numa chamada só; a 2ª chamada só reescreve
    os reprovados, com os motivos. Sem post esperando texto, não chama (zero token)."""
    res = {r: {} for r in redes}
    for tentativa in (1, 2):
        pends = {r: pendentes_da_rodada(pasta, r)[1] for r in redes}
        pends = {r: p for r, p in pends.items() if p}
        if not pends:
            break
        resp = escritor(montar_pacote(pasta, c, pends, False, ENTREGA_SO_JSON))
        for r, parte in separar_resposta(resp, list(pends)).items():
            res[r][f"escrita_{tentativa}"] = aplicar_escrita(pasta, c, r, parte)
    return res


def cmd_escrever(args):
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    try:
        resp = json.loads(Path(args.arquivo).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise Erro(f"não consegui ler {args.arquivo}: {e}")
    if not isinstance(resp, dict):
        raise Erro('a resposta do escritor precisa ser um objeto JSON {"<id>": "texto"}')
    if args.rede:
        out(aplicar_escrita(pasta, c, args.rede, resp))
        return 0
    out({r: aplicar_escrita(pasta, c, r, parte) for r, parte in separar_resposta(resp, redes).items() if parte})
    return 0


def aplicar_escrita(pasta, c, rede, resp):
    """Valida o que o escritor entregou ({id: texto | "-motivo"}) e grava: rascunho (e aprovado, no
    modo sozinho), pulado, ou reprovado (volta no próximo lote; na 2ª reprovação, pulado)."""
    cfg = rede_cfg(c, rede)
    rd = rodada_dir(pasta, rede)
    simular, dados = rodada_atual(pasta, rede)
    if not dados:
        raise Erro("não há rodada coletada nesta rede")
    if not isinstance(resp, dict):
        raise Erro('a resposta do escritor precisa ser um objeto JSON {"<id>": "texto"}')
    evs = eventos(pasta, rede)
    reg = R.estados(evs)
    textos_sim = ler_json(rd / "textos.json", {}) or {}
    pend = {p["id"] for p in pendentes(simular, dados, reg, textos_sim)}
    voz = voz_atual(pasta, rede) or ""
    corpus = R.corpus_recente(reg, agora())
    abert = R.aberturas_recentes(reg)
    proib = proibidas(c, rede, evs)
    tent = ler_json(rd / "tentativas.json", {}) or {}
    reprov, aceitos, pulados = {}, 0, 0
    for pid, val in resp.items():
        pid = str(pid)
        if pid not in pend:
            continue
        val = str(val or "").strip()
        if val.startswith("-"):
            pular(pasta, rede, pid, val[1:].strip() or "pulado pelo escritor", simular, textos_sim)
            pulados += 1
            continue
        motivos = R.validar(val, recentes=corpus, proibidas=proib, emoji_ok=emoji_permitido(voz),
                            aberturas=abert, nomes=nomes_da_conta(c))
        if motivos:
            tent[pid] = tent.get(pid, 0) + 1
            if tent[pid] >= 2:
                pular(pasta, rede, pid, "pós-check: " + motivos[0], simular, textos_sim)
                pulados += 1
            else:
                reprov[pid] = motivos
            continue
        aceitos += 1
        corpus.append(val)
        abert.append(R.abertura(val))
        if simular:
            textos_sim[pid] = {"texto": val}
        else:
            registrar(pasta, rede, "rascunho", id=pid, texto=val, voz=versao_voz(pasta, rede))
            if cfg.get("modo") == "sozinho":
                registrar(pasta, rede, "aprovado", id=pid)
    gravar_json(rd / "tentativas.json", tent)
    gravar_json(rd / "reprovados.json", reprov)
    if simular:
        gravar_json(rd / "textos.json", textos_sim)
    faltam = [p["id"] for p in pendentes(simular, dados, R.estados(eventos(pasta, rede)), textos_sim)]
    return {"aceitos": aceitos, "pulados": pulados, "reprovados": reprov, "faltam": faltam,
            "modo": "simulação" if simular else cfg.get("modo")}


# --------------------------------------------------------------------------------------------
# Revisão no chat e aprovação (com aprendizado)
# --------------------------------------------------------------------------------------------
def _linha_revisao(n, nome, trecho, data, t, comentario):
    return f'{n}. {nome or "?"} · "{limpar_texto(trecho or "", 90)}" ({idade_txt(data, t)})\n   → {comentario}'


def cmd_revisao(args):
    """A fila numerada para o chat. Sem --rede, as duas redes numa lista só (numeração seguida)."""
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    t = agora()
    mapa, blocos, n = {}, [], 0
    for rede in redes:
        simular, dados = rodada_atual(pasta, rede)
        linhas = []
        if simular:
            textos = ler_json(rodada_dir(pasta, rede) / "textos.json", {}) or {}
            por_id = {p["id"]: p for p in (dados or {}).get("posts") or []}
            linhas.append("SIMULAÇÃO: nada foi gravado nem será postado.")
            for pid, v in textos.items():
                n += 1
                p = por_id.get(pid, {})
                linhas.append(_linha_revisao(n, p.get("nome"), p.get("texto"), p.get("data"), t,
                                             v.get("texto") or f"(pulado: {v.get('pular')})"))
        else:
            vencer(pasta, rede)
            reg = R.estados(eventos(pasta, rede))
            for pid, r in sorted(((pid, r) for pid, r in reg.items() if r["estado"] == "rascunho"),
                                 key=lambda x: x[1].get("selecionado_em") or ""):
                n += 1
                mapa[str(n)] = [rede, pid]
                linhas.append(_linha_revisao(n, r.get("nome"), r.get("trecho"), r.get("data"), t, r.get("texto")))
        if linhas:
            blocos.append((f"{ROTULO[rede]}:\n" if len(redes) > 1 else "") + "\n".join(linhas))
    gravar_json(arq(pasta, "rodada", "revisao.json"), mapa)
    out("\n\n".join(blocos) if blocos else "Nada esperando revisão.")
    return 0


def cmd_aprovar(args):
    """Aplica as decisões da revisão (o "ok" de "todos" vale para as duas redes). Sem --rede, a saída é
    por rede."""
    pasta, c = carregar(args)
    mapa = ler_json(arq(pasta, "rodada", "revisao.json"), {}) or {}
    if args.rede:
        mapa = {n: v for n, v in mapa.items() if v[0] == args.rede}
    if not mapa:
        raise Erro("não há revisão aberta (rode revisao antes)")
    dec = ler_json(args.arquivo)
    if not isinstance(dec, dict):
        raise Erro("o arquivo de decisões precisa ser um objeto JSON")
    por_rede = {}
    for n, (rede, pid) in mapa.items():
        por_rede.setdefault(rede, []).append((n, pid))
    res = {rede: aprovar_rede(pasta, c, rede, itens, dec) for rede, itens in por_rede.items()}
    sincronizar_planilha(pasta, c)
    out(res[args.rede] if args.rede else res)
    return 0


def aprovar_rede(pasta, c, rede, itens, dec):
    cfg = rede_cfg(c, rede)
    evs = eventos(pasta, rede)
    reg = R.estados(evs)
    t = agora()
    antes_proib = set(proibidas(c, rede, evs))
    voz = voz_atual(pasta, rede) or ""
    aprov = edit = desc = decididos = 0
    avisos = {}
    for n, pid in itens:
        d = dec.get(n, dec.get("todos"))
        r = reg.get(pid)
        if d is None or not r or r["estado"] != "rascunho":
            continue
        d = str(d).strip()
        if d.lower() == "ok":
            registrar(pasta, rede, "aprovado", id=pid)
            aprov += 1
        elif d.startswith("-"):
            registrar(pasta, rede, "descartado", id=pid, motivo=d[1:].strip() or None, texto=r.get("texto"))
            desc += 1
        else:
            forcar = d.startswith("!")
            novo = d[1:].strip() if forcar else d
            motivos = R.validar(novo, recentes=R.corpus_recente(reg, t, excluir=pid),
                                proibidas=sorted(antes_proib), emoji_ok=emoji_permitido(voz),
                                nomes=nomes_da_conta(c))
            if motivos and not forcar:
                avisos[n] = motivos
                continue
            registrar(pasta, rede, "editado", id=pid, antes=r.get("texto"), depois=novo,
                      forcado=True if forcar else None)
            edit += 1
        decididos += 1
    if decididos:
        registrar(pasta, rede, "revisao", n=decididos, editados=edit, descartados=desc)
    evs2 = eventos(pasta, rede)
    desde = data_da_voz(pasta, rede) or ""
    aprendizados = (len(pares_de_edicao(evs2, desde or None))
                    + sum(1 for e in evs2 if e.get("ev") in ("descartado", "nota") and e.get("quando", "") >= desde))
    return {"aprovados": aprov, "editados": edit, "descartados": desc,
         "esperando": sum(1 for r in R.estados(evs2).values() if r["estado"] == "rascunho"),
         "avisos": avisos, "limpa": R.rodada_limpa(decididos, edit, desc) if decididos else None,
         "propor_sozinho": cfg.get("modo") == "revisao" and R.propor_sozinho(evs2),
         "novas_proibidas": sorted(set(proibidas(c, rede, evs2)) - antes_proib),
         "aprendizados_desde_a_voz": aprendizados}


# --------------------------------------------------------------------------------------------
# Postar: curtir e comentar a fila aprovada, conferindo cada passo (o mesmo laço nas duas redes)
# --------------------------------------------------------------------------------------------
def parar(pasta, rede, res, motivo, pausar=True):
    if pausar:
        registrar(pasta, rede, "parada", motivo=motivo)
    res["parou"] = motivo


def _parou_por_bloqueio(pasta, rede, page, A, res, onde):
    b = A.bloqueio(page)
    if b == "SESSAO":
        marcar_sessao(pasta, rede, False)
        parar(pasta, rede, res, f"a sessão caiu {onde}: refaça o login", pausar=False)
        return True
    if b:
        parar(pasta, rede, res, f"{b} {onde}: rede parada até amanhã (não resolvo captcha)")
        return True
    return False


def ja_comentado_linkedin(page, voy, me, it, A):
    """Motivo (str) se há prova de que a conta JÁ comentou, ou se não dá para provar que não;
    'bloqueio' se a leitura deu sinal de bloqueio; None libera. É o portão final da regra nº 1."""
    n = it.get("n_comentarios")
    if n is not None and n > 100:
        return "post com mais de 100 comentários: não dá para provar que a conta não comentou"
    leu = False
    try:
        if voy.comentario_da_conta(it["id"], me):
            return "a conta já comentou neste post (Voyager)"
        leu = True
    except A.VoyagerErro as e:
        if e.tipo in (A.ERRO_BLOQUEIO, A.ERRO_SESSAO):
            return "bloqueio"
    if (A.comentarios_na_pagina(page, me.get("vanity")) or {}).get("da_conta"):
        return "a conta já comentou neste post (página)"
    if not leu and (n is None or n > 0):
        return "não consegui ler os comentários e o post tem comentários: sem prova, não comento"
    return None


def ja_respondido_x(page, meu, respondidos, it, A):
    """O mesmo portão no X: as respostas da conta (aba de respostas do perfil, lida nesta rodada) e a
    própria página do post."""
    if it["id"] in respondidos or (it.get("canon") or "") in respondidos:
        return "a conta já respondeu este post (respostas da conta)"
    pag = A.respostas_na_pagina(page, meu) or {}
    if pag.get("da_conta"):
        return "a conta já respondeu este post (página)"
    if pag.get("erro"):
        return "não consegui ler as respostas do post: sem prova, não respondo"
    return None


def postar_linkedin(pasta, c, fila, page, voy, me, acoes=None, dormir=time.sleep, rng=random,
                    tocar=lambda: None, relogio=time.monotonic, so_passos=False):
    if acoes is None:
        import linkedin as acoes
    A = acoes

    def link(it):
        try:
            achado = voy.comentario_da_conta(it["id"], me)
        except A.VoyagerErro:
            return None                         # o link é detalhe, não prova: segue sem ele
        return A.url_do_comentario(f"urn:li:activity:{it['id']}", achado["comment_urn"]) if achado else None
    g = _postar(pasta, c, "linkedin", fila, page, A, me.get("vanity"),
                lambda it: ja_comentado_linkedin(page, voy, me, it, A), link, rng=rng, tocar=tocar, relogio=relogio)
    return g if so_passos else rodar_juntos({"linkedin": g}, dormir, relogio)["linkedin"]


def postar_x(pasta, c, fila, page, meu, respondidos, acoes=None, dormir=time.sleep, rng=random,
             tocar=lambda: None, relogio=time.monotonic, so_passos=False):
    if acoes is None:
        import x as acoes
    A = acoes
    g = _postar(pasta, c, "x", fila, page, A, meu,
                lambda it: ja_respondido_x(page, meu, respondidos, it, A),
                lambda it: (A.respostas_na_pagina(page, meu, " ".join(it["texto"].split())[:40]) or {}).get("link"),
                rng=rng, tocar=tocar, relogio=relogio)
    return g if so_passos else rodar_juntos({"x": g}, dormir, relogio)["x"]


def rodar_juntos(passos, dormir=time.sleep, relogio=time.monotonic):
    """As postagens das redes ao mesmo tempo, no mesmo navegador (uma aba por rede): cada gerador
    devolve a pausa que quer depois de um post e, enquanto uma rede espera a dela, a outra age. As
    pausas de cada rede continuam as dela. Um dict no lugar do gerador já é o resultado. {rede: res}"""
    res, fila = {}, []
    for rede, g in passos.items():
        if isinstance(g, dict):
            res[rede] = g
        else:
            fila.append((relogio(), rede, g))
    while fila:
        fila.sort(key=lambda x: x[0])
        quando, rede, g = fila.pop(0)
        if quando > relogio():
            dormir(quando - relogio())
        try:
            fila.append((relogio() + next(g), rede, g))
        except StopIteration as fim:
            res[rede] = fim.value
        except Exception as e:  # noqa: BLE001 - uma rede que cai não derruba a outra
            res[rede] = dict(erro_dict(erro_inesperado(e)), comentados=[])
    return res


FALHAS_GUARDADAS = 30


def foto_da_falha(pasta, rede, page, pid, etapa):
    """Um print da tela quando o clique não deu certo, para ver o que estava na frente (só no PC, em
    rodada/<rede>/falhas, os 30 mais recentes). Nunca atrapalha a rodada."""
    try:
        pasta_f = arq(pasta, "rodada", rede, "falhas")
        pasta_f.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(pasta_f / f"{agora().strftime('%Y%m%d-%H%M%S')}-{pid}-{etapa}.png"), timeout=10000)
        for velha in sorted(pasta_f.glob("*.png"))[:-FALHAS_GUARDADAS]:
            velha.unlink()
    except Exception:  # noqa: BLE001
        pass


def _post_na_tela(page, A, pid, tentativas=8, pausa_ms=2000):
    """O post montou na tela? A rede monta aos poucos (o LinkedIn novo leva ~10 s, visto em 12/11/2026):
    tenta por até ~16 s e, na metade, recarrega a página uma vez antes de desistir."""
    for i in range(tentativas):
        if (A.controles(page, pid) or {}).get("achou_post"):
            return True
        if i < tentativas - 1:
            try:
                if i == tentativas // 2 - 1:
                    page.reload(wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(pausa_ms)
            except Exception:  # noqa: BLE001
                return False
    return False


def erro_inesperado(e):
    """Um erro que não é do Replai (timeout do Playwright, aba ou navegador fechado) vira Erro com um
    motivo curto, para a rodada e o vigia relatarem em vez de cair sem saída."""
    if isinstance(e, Erro):
        return e
    nome = type(e).__name__
    linha = (str(e).strip().splitlines() or [""])[0][:200]
    texto = "a página demorou demais para responder" if "Timeout" in nome else f"falha inesperada ({nome})"
    return Erro(f"{texto}: {linha}" if linha else texto, 2)


def _postar(pasta, c, rede, fila, page, A, me_chave, ja_comentado, link_do_comentario,
            rng=random, tocar=lambda: None, relogio=time.monotonic):
    """Gerador: um post por vez (abre, confere bloqueio e tela, curte, confere que a conta ainda não
    comentou, comenta e confere) e devolve (yield) a pausa que quer antes do próximo; o resultado sai no
    return. Intenção gravada ANTES de cada clique. Cotas reavaliadas a cada post.
    `A` é o módulo da rede (bloqueio, controles, curtir, comentar)."""
    cfg = c["redes"][rede]
    voz = voz_atual(pasta, rede) or ""
    inicio = relogio()
    res = {"comentados": [], "curtidos": 0, "ja_comentados": [], "incertos": [], "pulados": [],
           "erros": [], "parou": None, "fim": None}
    telas_ruins = 0
    fila = list(fila)
    rng.shuffle(fila)                   # ritmo humano: a ordem da rodada não segue a da seleção
    if rede == "x" and fila:            # aquece o SPA do X: a 1ª abertura fria não renderiza o post
        try:
            page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_selector("article", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
    for i, it in enumerate(fila):
        tocar()
        if (relogio() - inicio) / 60 > R.MAX_RODADA_MIN:
            res["fim"] = "tempo máximo da rodada"
            break
        evs = eventos(pasta, rede)
        cot = R.cotas(rede, agora(), evs, cfg.get("teto"))
        if cot["comentarios"] <= 0 and cot["curtidas"] <= 0:
            res["fim"] = cot["motivo"]
            break
        pid, nome = it["id"], it.get("nome") or it.get("autor") or "?"
        try:
            page.goto(it["url"], wait_until="domcontentloaded", timeout=30000)
            if rede == "x":                     # o X carrega o tweet por API; espera o conteúdo (recarrega 1x se vazio)
                for _tent in range(2):
                    try:
                        page.wait_for_selector("article", timeout=18000)
                        break
                    except Exception:  # noqa: BLE001
                        if _tent == 0:
                            try:
                                page.reload(wait_until="domcontentloaded", timeout=30000)
                            except Exception:  # noqa: BLE001
                                break
            page.wait_for_timeout(int(rng.uniform(3000, 5000)))
        except Exception as e:  # noqa: BLE001
            res["erros"].append(f"{nome}: abrir o post falhou ({type(e).__name__})")
            continue
        try:
            page.mouse.wheel(0, int(rng.uniform(200, 700)))      # rola antes de agir, como gente
            page.wait_for_timeout(int(rng.uniform(800, 2000)))
        except Exception:  # noqa: BLE001
            pass
        if _parou_por_bloqueio(pasta, rede, page, A, res, "na página do post"):
            break
        if not _post_na_tela(page, A, pid):
            foto_da_falha(pasta, rede, page, pid, "tela")
            telas_ruins += 1
            res["erros"].append(f"{nome}: tela do post irreconhecível")
            if telas_ruins >= 3:
                parar(pasta, rede, res, "3 telas de post irreconhecíveis seguidas (a rede mudou a página: "
                                        "rode calibrar)", pausar=False)
                break
            continue
        telas_ruins = 0
        comentou = False
        if not it.get("curtiu") and cot["curtidas"] > 0:
            registrar(pasta, rede, "intencao", id=pid, acao="curtir")
            ok, motivo, fase = A.curtir(page, pid)
            registrar(pasta, rede, "confirmado" if ok else ("desistiu" if fase == "pre_clique" else "incerto"),
                      id=pid, acao="curtir", motivo=None if ok else motivo)
            if ok:
                res["curtidos"] += 1
            else:
                foto_da_falha(pasta, rede, page, pid, "curtir")
            if _parou_por_bloqueio(pasta, rede, page, A, res, "depois de curtir"):
                break
            page.wait_for_timeout(int(rng.uniform(2000, 5000)))
        if it["comentar"] and cot["comentarios"] > 0:
            motivos = []
            if not it.get("forcado"):
                reg = R.estados(eventos(pasta, rede))
                motivos = R.validar(it["texto"], recentes=R.corpus_recente(reg, agora(), excluir=pid),
                                    proibidas=proibidas(c, rede, evs), emoji_ok=emoji_permitido(voz),
                                    nomes=nomes_da_conta(c))
            ja = None if motivos else ja_comentado(it)
            if motivos:
                registrar(pasta, rede, "pulado", id=pid, motivo="pós-check na hora: " + motivos[0])
                res["pulados"].append({"nome": nome, "motivo": motivos[0]})
            elif ja == "bloqueio":
                parar(pasta, rede, res, "bloqueio na leitura dos comentários")
                break
            elif ja:
                registrar(pasta, rede, "ja_comentado", id=pid, motivo=ja)
                res["ja_comentados"].append({"nome": nome, "motivo": ja})
            else:
                registrar(pasta, rede, "intencao", id=pid, acao="comentar", texto=it["texto"])
                ok, motivo, fase = A.comentar(page, pid, it["texto"], me_chave, rng)
                link = None
                if ok or fase == "pos_clique":
                    try:
                        link = link_do_comentario(it)
                    except Exception:  # noqa: BLE001 - o link é detalhe, não prova
                        link = None
                    if not ok and link:
                        # a tela não confirmou (o layout muda), mas a rede já lista o comentário da conta
                        # neste post: isso é prova, não palpite
                        ok, motivo = True, "ok (confirmado pela lista de comentários)"
                if ok:
                    registrar(pasta, rede, "confirmado", id=pid, acao="comentar", link=link)
                    res["comentados"].append({"nome": nome, "texto": it["texto"], "url": it.get("url")})
                    comentou = True
                elif fase == "pre_clique":
                    foto_da_falha(pasta, rede, page, pid, "comentar")
                    registrar(pasta, rede, "desistiu", id=pid, acao="comentar", motivo=motivo)
                    res["erros"].append(f"{nome}: o comentário não saiu ({motivo})")
                else:
                    foto_da_falha(pasta, rede, page, pid, "comentar")
                    registrar(pasta, rede, "incerto", id=pid, acao="comentar", motivo=motivo)
                    res["incertos"].append({"nome": nome, "url": it.get("url"), "motivo": motivo})
                if _parou_por_bloqueio(pasta, rede, page, A, res, "depois de comentar"):
                    break
        if i < len(fila) - 1:
            yield R.pausa(rede, comentou, rng)
    res["sobrou_na_fila"] = len(R.fila_de_postagem(R.estados(eventos(pasta, rede))))
    return res


def fila_para_postar(pasta, c, rede, so=None):
    """(fila, cotas) do que dá para postar agora; fila vazia quando não há nada ou não cabe."""
    vencer(pasta, rede)
    evs = eventos(pasta, rede)
    fila = R.fila_de_postagem(R.estados(evs), so=None if so in (None, "primeiro") else so)
    if so == "primeiro":
        fila = [i for i in fila if i["comentar"]][:1]
    return fila, R.cotas(rede, agora(), evs, rede_cfg(c, rede).get("teto"))


def passos_de_postar(pasta, c, rede, fila, page, leitor, acoes=None, rng=random, tocar=lambda: None):
    """O gerador da postagem de uma rede, com a conta conferida (e, no X, as respostas da conta lidas)."""
    if rede == "x":
        import x as X
        try:
            meu = leitor.me()
            conferir_conta(pasta, c, rede, meu)
            respondidos = X.respondidos(leitor.respostas_da_conta(meu), meu)
        except X.ErroX as e:
            raise erro_x(pasta, e, "o X não abriu")
        return postar_x(pasta, c, fila, page, meu, respondidos, acoes=acoes, rng=rng, tocar=tocar, so_passos=True)
    import linkedin as L
    try:
        me = leitor.me()
    except L.VoyagerErro as e:
        if e.tipo == L.ERRO_SESSAO:
            marcar_sessao(pasta, rede, False)
            raise ErroSessao(f"não consegui ler a conta logada: {e}")
        raise Erro(f"não consegui ler a conta logada: {e}", 2)
    conferir_conta(pasta, c, rede, me.get("vanity"))
    return postar_linkedin(pasta, c, fila, page, leitor, me, acoes=acoes, rng=rng, tocar=tocar, so_passos=True)


def cmd_postar(args):
    """Sem --rede, as redes ligadas ao mesmo tempo, no mesmo navegador."""
    pasta, c = carregar(args)
    res, filas = {}, {}
    for rede in redes_pedidas(c, args.rede):
        fila, cot = fila_para_postar(pasta, c, rede, args.so)
        if not fila:
            res[rede] = {"nada_a_fazer": "fila vazia (nada aprovado nem para curtir)"}
        elif cot["comentarios"] <= 0 and cot["curtidas"] <= 0:
            res[rede] = {"nada_a_fazer": cot["motivo"]}
        elif args.simular:
            res[rede] = {"simulacao": True, "cota": cot, "so_curtiria": sum(1 for i in fila if not i["comentar"]),
                         "comentaria": [{"nome": i.get("nome"), "url": i.get("url"), "texto": i.get("texto")}
                                        for i in fila if i["comentar"]][:cot["comentarios"]]}
        else:
            filas[rede] = fila
    if filas:
        from playwright.sync_api import sync_playwright
        with Trava(trava_de(pasta, c, next(iter(filas)))) as trava, sync_playwright() as pw:
            ctx, abertas, erros = abrir_redes(pasta, c, pw, list(filas))
            try:
                res.update({r: erro_dict(e) for r, e in erros.items()})
                passos = {}
                for rede, (page, leitor) in abertas.items():
                    try:
                        passos[rede] = passos_de_postar(pasta, c, rede, filas[rede], page, leitor, tocar=trava.tocar)
                    except Exception as e:  # noqa: BLE001
                        res[rede] = erro_dict(erro_inesperado(e))
                res.update(rodar_juntos(passos))
            finally:
                fechar(ctx)
        planilha = sincronizar_planilha(pasta, c)
        for rede in filas:
            if "erro" not in res[rede]:
                res[rede]["planilha_atualizada"] = planilha
    return saida_redes(args.rede, res)


def _testar_linkedin(pasta, c, page, voy, item):
    import linkedin as L
    perfis, post = perfis_da_rede(pasta, c, "linkedin"), {}

    def conta():
        me = voy.me()
        if conferir_conta(pasta, c, "linkedin", me.get("vanity")):
            return None, f"{me.get('vanity')}: conta aprendida agora, confirme com quem opera"
        return True, me.get("vanity")

    def leitura():
        if not perfis:
            return False, "a lista está vazia"
        mortos = []                       # perfil apagado/renomeado (404/403 avulso) não reprova a lista
        for pf in perfis[:5]:
            try:
                posts = voy.posts(voy.urn_do_perfil(pf["chave"]), count=5)
            except L.VoyagerErro as e:
                if e.tipo in (L.ERRO_BLOQUEIO, L.ERRO_SESSAO):
                    raise
                mortos.append(pf["chave"])
                continue
            post.update(next((p for p in posts if not p.get("repost_puro")), {}))
            extra = f" (pulei {len(mortos)} sem perfil: {', '.join(mortos)})" if mortos else ""
            return True, f"{pf['nome']}: {len(posts)} posts lidos" + extra
        return False, f"os {len(mortos)} primeiros perfis não abriram ({', '.join(mortos)}): confira a lista"

    def botoes():
        if not post:
            return None, "nenhum post para abrir (a primeira pessoa da lista não postou nada recente)"
        page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
        _post_na_tela(page, L, post["activity_id"])          # o LinkedIn novo monta o post em ~10 s
        return _botoes_ok(L, page, post["activity_id"])

    def notificacoes():
        n = len(L.posts_das_notificacoes(page))
        return (True, f"{n} avisos de post lidos") if n else (None, "nenhum aviso de post lido (normal se ninguém "
                                                                      "com sininho ligado postou; se for, a página mudou)")

    def sino():
        if not perfis:
            return False, "a lista está vazia"
        for pf in perfis[:3]:             # pula perfil morto, igual à leitura
            page.goto(f"https://www.linkedin.com/in/{pf['chave']}/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(4500)
            s = L.sininho(page)
            if not s.get("achou_perfil"):
                continue
            if not s.get("achou_sino"):
                return False, "sininho não achado (botões: " + ", ".join(s.get("botoes") or [])[:120] + ")"
            return True, "ligado" if s.get("ligado") else "achado (ainda desligado)"
        return False, "os primeiros perfis não abriram: confira a lista"

    item("LinkedIn: a conta logada é a certa", conta)
    item("LinkedIn: ler a lista", leitura)
    item("LinkedIn: curtir e comentar num post (sem clicar)", botoes)
    item("LinkedIn: notificações (vigia)", notificacoes)
    item("LinkedIn: sininho num perfil da lista (sem clicar)", sino)


def _testar_x(pasta, c, page, leitor, item):
    import x as X
    post = {}

    def conta():
        meu = leitor.me()
        if not meu:
            return False, "não consegui ler a conta logada"
        if conferir_conta(pasta, c, "x", meu):
            return None, f"@{meu}: conta aprendida agora, confirme com quem opera"
        return True, "@" + meu

    def leitura():
        fontes = fontes_x(pasta, c)
        if not fontes:
            return False, "nenhuma Lista do X nem @ na planilha"
        f = fontes[0]
        tweets = leitor.lista(f["url"]) if f["tipo"] == "lista" else leitor.busca(f["handles"])
        post.update(next((t for t in tweets if not t.get("retweet_de")), {}))
        return True, f"{len(tweets)} posts lidos ({'Lista do X' if f['tipo'] == 'lista' else 'busca pelos @'})"

    def botoes():
        if not post:
            return None, "nenhum post para abrir (ninguém da lista postou nada recente)"
        page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
        for _tent in range(2):          # o X carrega o tweet por API; espera o conteúdo (recarrega 1x se vazio)
            try:
                page.wait_for_selector("article", timeout=18000)
                break
            except Exception:  # noqa: BLE001
                if _tent == 0:
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=30000)
                    except Exception:  # noqa: BLE001
                        break
        return _botoes_ok(X, page, post["id"])

    item("X: a conta logada é a certa", conta)
    item("X: ler a lista", leitura)
    item("X: curtir e responder num post (sem clicar)", botoes)


def _botoes_ok(M, page, pid):
    b = M.bloqueio(page)
    if b:
        return False, f"{b} na página do post"
    k = M.controles(page, pid) or {}
    if k.get("achou_post") and (k.get("like") or {}).get("achou") and (k.get("comentar") or {}).get("achou"):
        return True, "achados"
    return False, "a tela mudou: " + json.dumps(k, ensure_ascii=False)[:160]


def cmd_testar(args):
    """Confere tudo no PC e na tela real, SEM postar e sem clicar: navegador, listas, sessão e conta de
    cada rede, leitura da lista, botões num post de verdade, notificações e sininho do LinkedIn, o Claude
    Code em segundo plano e a tarefa do vigia. Cada item: ok true, false (problema) ou null (confira).
    Um item que falha não para os outros."""
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    itens = []

    def item(o_que, f):
        try:
            ok, detalhe = f()
        except Exception as e:  # noqa: BLE001 - o teste relata, não para
            ok, detalhe = False, f"{type(e).__name__}: {str(e)[:160]}"
        itens.append({"o_que": o_que, "ok": ok, "detalhe": detalhe})

    item("navegador do PC", lambda: (True, caminho_chrome() or "o próprio do Replai (Chromium)"))
    for rede in redes:
        def lista(rede=rede):
            n = len(perfis_da_rede(pasta, c, rede))
            x_lista = rede == "x" and any(li.get("x_lista") for li in c.get("listas") or []
                                          if li["rede"] == "x" and li.get("ativa", True))
            return n > 0 or x_lista, f"{n} pessoas" + (" + Lista do X" if x_lista else "")
        item(f"{ROTULO[rede]}: lista", lista)
    from playwright.sync_api import sync_playwright
    with Trava(trava_de(pasta, c, redes[0])), sync_playwright() as pw:
        ctx, abertas, erros = abrir_redes(pasta, c, pw, redes, fora_da_tela=True)
        try:
            for rede in redes:
                if rede in erros:
                    itens.append({"o_que": f"{ROTULO[rede]}: logado", "ok": False, "detalhe": str(erros[rede])})
                    continue
                itens.append({"o_que": f"{ROTULO[rede]}: logado", "ok": True, "detalhe": ""})
                page, leitor = abertas[rede]
                (_testar_x if rede == "x" else _testar_linkedin)(pasta, c, page, leitor, item)
        finally:
            fechar(ctx)
    com_vigia = [r for r in redes if rede_cfg(c, r).get("vigia")]

    def claude():
        if not claude_instalado():
            return (False if com_vigia else None), "Claude Code de linha de comando não instalado (o vigia precisa)"
        r = escrever_com_claude('Responda só com este JSON: {"ok": "ok"}', timeout=120)
        return r.get("ok") == "ok", f"respondeu (jeito {MODO_CLAUDE['modo']})"

    def tarefa():
        if not com_vigia:
            return None, "vigia desligado"
        cod, _saida = tarefa_do_vigia("consultar")
        return cod == 0, "agendamento do vigia ativo" if cod == 0 else "o agendamento sumiu: rode 'vigia --ligar'"

    item("Claude Code em segundo plano (vigia)", claude)
    item("tarefa do vigia", tarefa)
    tudo_ok = all(i["ok"] is not False for i in itens)
    out({"tudo_ok": tudo_ok, "itens": itens})
    return 0 if tudo_ok else 2


def cmd_calibrar(args):
    """Abre até 3 posts da última coleta e mostra o que a tela tem (controles e bloqueio), SEM clicar."""
    pasta, c = carregar(args)
    rede = args.rede
    rede_cfg(c, rede)
    _sim, dados = rodada_atual(pasta, rede)
    alvos = ((dados or {}).get("posts") or [])[:3]
    if not alvos and rede != "linkedin":
        raise Erro("rode 'coletar --simular' antes: o calibrar usa os posts da última coleta")
    from playwright.sync_api import sync_playwright
    import linkedin as L
    import x as X
    M = X if rede == "x" else L
    achados = []
    with Trava(trava_de(pasta, c, rede)), sync_playwright() as pw:
        ctx, page, _leitor = abrir_rede(pasta, c, pw, rede)
        try:
            if rede == "x" and alvos:          # aquece o SPA do X: a 1ª abertura fria não renderiza o post
                try:
                    page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_selector("article", timeout=15000)
                except Exception:  # noqa: BLE001
                    pass
            for p in alvos:
                page.goto(p["url"], wait_until="domcontentloaded", timeout=30000)
                if rede == "x":                # o X carrega o tweet por API; espera o conteúdo (recarrega 1x se vazio)
                    for _tent in range(2):
                        try:
                            page.wait_for_selector("article", timeout=18000)
                            break
                        except Exception:  # noqa: BLE001
                            if _tent == 0:
                                try:
                                    page.reload(wait_until="domcontentloaded", timeout=30000)
                                except Exception:  # noqa: BLE001
                                    break
                page.wait_for_timeout(2000)
                if rede == "linkedin":
                    _post_na_tela(page, L, p["id"])
                achados.append({"nome": p["nome"], "url": p["url"], "controles": M.controles(page, p["id"]),
                                "bloqueio": M.bloqueio(page)})
            extra = {}
            if rede == "linkedin":                 # o que o vigia do LinkedIn enxerga, sem clicar
                membros = {pf["chave"] for pf in perfis_da_rede(pasta, c, rede)}
                avisos = L.posts_das_notificacoes(page)
                extra["avisos_lidos"] = len(avisos)
                extra["avisos_da_lista"] = [a for a in avisos if a.get("vanity") in membros][:10]
                extra["avisos_exemplo"] = avisos[:5]
                primeiro = next(iter(perfis_da_rede(pasta, c, rede)), None)
                if primeiro:
                    page.goto(f"https://www.linkedin.com/in/{primeiro['chave']}/", wait_until="domcontentloaded",
                              timeout=30000)
                    page.wait_for_timeout(4500)
                    extra["sininho"] = dict(L.sininho(page), perfil=primeiro["chave"])
        finally:
            fechar(ctx)
    out({"calibrar": achados, **extra})
    return 0


# --------------------------------------------------------------------------------------------
# Voz: amostra da própria conta, pacotes do subagente de voz e gravação versionada
# --------------------------------------------------------------------------------------------
def amostra_de(pasta, c, rede, page, leitor):
    """Posts e comentários da própria conta numa rede, para o retrato da voz."""
    import linkedin as L
    import x as X
    if rede == "x":
        try:
            meu = leitor.me()
            conferir_conta(pasta, c, rede, meu)
            proprios = [t for t in leitor.perfil(meu) if t["autor"] == meu]
            respostas = [t for t in leitor.respostas_da_conta(meu) if t["autor"] == meu]
        except X.ErroX as e:
            raise erro_x(pasta, e, "a leitura falhou")
        posts = [{"texto": t["texto"], "repost_puro": bool(t.get("retweet_de"))}
                 for t in proprios if not t.get("resposta_a")]
        coment = [t["texto"] for t in respostas if t.get("resposta_a")]
    else:
        try:
            me = leitor.me()
            conferir_conta(pasta, c, rede, me.get("vanity"))
            # o feed de atividade traz post de outras pessoas (repost, menção): a voz é só do que a conta escreveu
            posts = [p for p in leitor.posts(me["urn"], count=20)
                     if (p.get("autor_vanity") or me["vanity"]).lower() == me["vanity"].lower()]
        except L.VoyagerErro as e:
            raise Erro(f"a leitura falhou: {e}", 4 if e.tipo == L.ERRO_BLOQUEIO else 2)
        coment = L.comentarios_proprios(page, me["vanity"])
    am = {"posts": [limpar_texto(p["texto"], 600) for p in posts
                    if (p.get("texto") or "").strip() and not p.get("repost_puro")],
          "comentarios": [limpar_texto(t, 400) for t in coment][:30]}
    gravar_json(arq(pasta, f"amostra-{rede}.json"), am)
    return {"posts": len(am["posts"]), "comentarios": len(am["comentarios"])}


def cmd_voz_amostra(args):
    """Sem --rede, as duas redes no mesmo navegador."""
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    from playwright.sync_api import sync_playwright
    with Trava(trava_de(pasta, c, redes[0])), sync_playwright() as pw:
        ctx, abertas, erros = abrir_redes(pasta, c, pw, redes)
        try:
            res = {r: erro_dict(e) for r, e in erros.items()}
            for rede, (page, leitor) in abertas.items():
                try:
                    res[rede] = amostra_de(pasta, c, rede, page, leitor)
                except Erro as e:
                    res[rede] = erro_dict(e)
        finally:
            fechar(ctx)
    return saida_redes(args.rede, res)


# --------------------------------------------------------------------------------------------
# Material de apoio da voz: arquivos que quem opera manda (bio, apresentação, artigo, página do site).
# O texto fica em <Conta>\material\ e entra no pacote da voz, abaixo do que a conta escreve de verdade.
# --------------------------------------------------------------------------------------------
MATERIAL_MAX_CHARS = 15000          # o que vai ao pacote da voz, somando os arquivos
FORMATOS_MATERIAL = "PDF, Word (.docx), MD, HTML ou TXT"
_HTML_FORA = ("script", "style", "noscript", "svg", "template")
_HTML_QUEBRA = ("p", "br", "li", "div", "h1", "h2", "h3", "h4", "h5", "tr", "section", "article", "blockquote")


def _texto_de_html(html):
    from html.parser import HTMLParser

    class Leitor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.partes, self.fora = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in _HTML_FORA:
                self.fora += 1
            elif tag in _HTML_QUEBRA:
                self.partes.append("\n")

        def handle_endtag(self, tag):
            if tag in _HTML_FORA and self.fora:
                self.fora -= 1

        def handle_data(self, dado):
            if not self.fora:
                self.partes.append(dado)

    leitor = Leitor()
    leitor.feed(html)
    return "".join(leitor.partes)


def texto_de_arquivo(caminho):
    """O texto corrido de um PDF, Word (.docx), Markdown, HTML ou texto, sem linhas em branco."""
    p = Path(caminho)
    ext = p.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            raise Erro("para ler PDF falta a biblioteca pypdf: rode o instalador do Replai de novo")
        texto = "\n".join(pg.extract_text() or "" for pg in PdfReader(str(p)).pages)
    elif ext == ".docx":
        import zipfile
        from xml.etree import ElementTree
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(p) as z:
            raiz = ElementTree.fromstring(z.read("word/document.xml"))
        texto = "\n".join("".join(t.text or "" for t in par.iter(f"{w}t")) for par in raiz.iter(f"{w}p"))
    elif ext in (".html", ".htm"):
        texto = _texto_de_html(p.read_text(encoding="utf-8", errors="replace"))
    elif ext in (".md", ".markdown", ".txt"):
        texto = p.read_text(encoding="utf-8", errors="replace")
    else:
        raise Erro(f"formato que o Replai não lê: use {FORMATOS_MATERIAL} (Word antigo .doc: salve como .docx)")
    linhas = (re.sub(r"[ \t\xa0]+", " ", linha).strip() for linha in texto.splitlines())
    return "\n".join(linha for linha in linhas if linha)


def material_da_conta(pasta):
    """O material guardado, arquivo por arquivo, até MATERIAL_MAX_CHARS no total."""
    partes, total = [], 0
    for f in sorted(arq(pasta, "material").glob("*.txt")):
        sobra = MATERIAL_MAX_CHARS - total
        if sobra <= 0:
            break
        texto = f.read_text(encoding="utf-8")[:sobra]
        partes.append(f"### {f.stem}\n{texto}")
        total += len(texto)
    return "\n\n".join(partes)


def cmd_material(args):
    pasta, c = carregar(args)
    res = {"lidos": [], "erros": []}
    for caminho in args.arquivo:
        p = Path(caminho.strip().strip('"'))
        try:
            if not p.is_file():
                raise Erro("não achei o arquivo")
            texto = texto_de_arquivo(p)
        except Erro as e:
            res["erros"].append(f"{p.name}: {e}")
            continue
        except Exception as e:  # noqa: BLE001  (arquivo corrompido, PDF com senha...)
            res["erros"].append(f"{p.name}: não consegui ler ({e})")
            continue
        if not texto:
            res["erros"].append(f"{p.name}: sem texto (PDF escaneado, só com imagem?)")
            continue
        destino = arq(pasta, "material", f"{p.stem}.txt")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        res["lidos"].append({"arquivo": p.name, "caracteres": len(texto)})
    res["no_pacote_da_voz"] = len(material_da_conta(pasta))
    out(res)
    return 2 if res["erros"] and not res["lidos"] else 0


# --------------------------------------------------------------------------------------------
# Cópia de segurança dos dados (dados.py): para trocar de PC ou recuperar uma pasta apagada
# --------------------------------------------------------------------------------------------
VERSAO = SCRIPT.parent.parent / "versao.json"      # gravado pelo instalador: commit e clone de origem


def cmd_atualizacao(args):
    """Há versão nova do Replai na main do GitHub? Compara a instalada com a main, pelo clone de onde
    ela veio (o repositório é privado: usa o login do GitHub que o clone já guardou, sem abrir janela).
    Com --aplicar, atualiza o clone e roda o instalador de novo (os dados não são tocados)."""
    import subprocess
    v = ler_json(VERSAO, {}) or {}
    origem = Path(v.get("origem") or ".")
    if not v.get("commit") or not (origem / ".git").is_dir():
        out({"atualizar": None, "motivo": "instalado sem o clone do GitHub: instale pelo link para receber avisos"})
        return 0
    amb = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")

    def git(*a):
        try:
            p = subprocess.run(["git", "-C", str(origem), *a], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=60, env=amb)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Erro(f"não consegui falar com o GitHub agora ({type(e).__name__})", 2)
        if p.returncode:
            raise Erro(f"o git recusou: {(p.stderr or p.stdout).strip()[-200:]}", 2)
        return p.stdout.strip()

    git("fetch", "--quiet", "origin", "main")
    nova = git("rev-parse", "origin/main")
    novidades = git("log", "--format=%s", f"{v['commit']}..origin/main").splitlines() if nova != v["commit"] else []
    res = {"instalada": v["commit"][:7], "nova": nova[:7], "atualizar": bool(novidades), "novidades": novidades[:10]}
    if args.aplicar and novidades:
        git("pull", "--ff-only", "--quiet", "origin", "main")
        p = subprocess.run([sys.executable, str(origem / "scripts" / "instalar.py")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1200)
        res["instalado"] = p.returncode == 0
        res["saida_do_instalador"] = (p.stdout or p.stderr or "").strip()[-600:]
        res["proximo"] = "abra uma conversa nova e digite /replai: a versão nova só carrega lá"
    out(res)
    return 0


def cmd_copia(args):
    """Faz uma cópia agora (o instalador faz uma sozinho antes de cada atualização) e lista as que há."""
    feita = D.fazer_copia(BASE, "manual")
    out({"feita": feita, "copias": D.copias(BASE), "pasta": str(BASE / D.COPIAS)})
    return 0


def cmd_restaurar(args):
    arquivo = Path(args.arquivo) if args.arquivo else next(map(Path, D.copias(BASE)), None)
    if not arquivo or not arquivo.is_file():
        raise Erro("não achei a cópia: passe --arquivo <caminho do .zip> (ou rode 'copia' para ver as que há)")
    res = D.restaurar(BASE, arquivo, substituir=args.substituir)
    if res["ja_existiam"]:
        res["aviso"] = ("estas contas já existiam neste PC e ficaram como estavam: "
                        + ", ".join(res["ja_existiam"]) + " (para trocar pela cópia: --substituir)")
    res["depois"] = "rode 'login': a sessão das redes não vai na cópia (cada PC loga de novo)"
    out(res)
    return 0


def _lista_md(itens, vazio):
    return [f"- {t}" for t in itens] or [f"- {vazio}"]


def cmd_voz_pacote(args):
    pasta, c = carregar(args)
    rede = args.rede
    voz = voz_atual(pasta, rede)
    molde = (REFS / ("formato-voz.en.md" if idioma() == "en" else "formato-voz.md")).read_text(encoding="utf-8")
    lingua = f"Idioma de quem opera: {idioma()}. Escreva a voz nesse idioma, com as seções do molde."
    if args.tipo == "retrato":
        redes = redes_pedidas(c, rede)
        partes = [f"# Retrato de voz · {c['nome']} · {' + '.join(ROTULO[r] for r in redes)}", lingua]
        if len(redes) > 1:
            partes.append("Uma voz por rede, da mesma pessoa: quem fala, assuntos, o que evita e valores são os "
                          "mesmos nas duas; o que muda é a forma de cada rede (tamanho, tom, emoji). Um arquivo "
                          "por rede, cada um completo.")
        for r in redes:
            am = ler_json(arq(pasta, f"amostra-{r}.json"))
            if not am:
                raise Erro(f"rode voz-amostra antes (a leitura do que a conta já escreveu no {ROTULO[r]})")
            partes += [f"## {ROTULO[r]}: amostra do que a conta escreveu",
                       "### Posts", *_lista_md(am.get("posts") or [], "nenhum lido"),
                       "### Comentários", *_lista_md(am.get("comentarios") or [], "nenhum lido")]
            if voz_atual(pasta, r):
                partes += [f"## {ROTULO[r]}: voz atual", voz_atual(pasta, r)]
        material = material_da_conta(pasta)
        if material:
            partes += ["## Material que quem opera mandou (bio, apresentação, artigos, site)",
                       "Serve para cargo, empresa, assuntos e valores. Jeito de escrever: o que a conta escreve "
                       "de verdade (a amostra) manda sobre o material.", material]
        partes += [molde, "## Onde gravar\n\nGrave a proposta, o arquivo de voz inteiro, com a ferramenta Write em:\n"
                   + "\n".join(f"- {ROTULO[r]}: {arq(pasta, f'rascunho-voz-{r}.md')}" for r in redes)]
        out("\n\n".join(partes))
        return 0
    else:
        if not rede:
            raise Erro("o aprendizado é por rede: passe --rede")
        if not voz:
            raise Erro("a conta ainda não tem voz nesta rede")
        evs = eventos(pasta, rede)
        desde = data_da_voz(pasta, rede) or ""
        novos = [e for e in evs if e.get("quando", "") >= desde]
        partes = [f"# Aprendizado · {c['nome']} · {rede}", lingua, "## Voz atual", voz,
                  "## Correções na revisão (antes e depois)",
                  *_lista_md([f"ANTES: {e['antes']}\n  DEPOIS: {e['depois']}" for e in novos
                              if e.get("ev") == "editado" and e.get("antes")], "nenhuma"),
                  "## Descartes (com motivo)",
                  *_lista_md([f"{e.get('motivo') or 'sem motivo'}: {e.get('texto') or ''}" for e in novos
                              if e.get("ev") == "descartado"], "nenhum"),
                  "## Notas depois de publicado",
                  *_lista_md([f"{e.get('nota')}: {e.get('texto') or ''}" for e in novos
                              if e.get("ev") == "nota"], "nenhuma"),
                  "## Palavras já proibidas automaticamente",
                  ", ".join(proibidas(c, rede, evs)) or "nenhuma", molde]
    partes.append("## Onde gravar\n\nGrave a proposta, o arquivo de voz inteiro, com a ferramenta Write em:\n"
                  f"{arq(pasta, f'rascunho-voz-{rede}.md')}")
    out("\n\n".join(partes))
    return 0


def cmd_voz(args):
    pasta, c = carregar(args)
    rede = args.rede
    try:
        novo = Path(args.arquivo).read_text(encoding="utf-8").strip()
    except OSError as e:
        raise Erro(f"não consegui ler {args.arquivo}: {e}")
    faltam = [pt for pt, en in SECOES_VOZ if pt not in novo and en not in novo]
    if faltam:
        raise Erro("a voz está sem as seções: " + ", ".join(faltam))
    if len(novo) > VOZ_MAX_CHARS:
        raise Erro(f"a voz tem {len(novo)} caracteres; o máximo é {VOZ_MAX_CHARS} (ela vai em todo lote)")
    atual, v = voz_atual(pasta, rede), versao_voz(pasta, rede)
    if atual:
        hist = arq(pasta, "voz-historico", f"voz-{rede}-v{v}.md")
        hist.parent.mkdir(parents=True, exist_ok=True)
        hist.write_text(atual, encoding="utf-8")
    corpo = novo.split("\n", 1)[1] if novo.startswith("# ") else novo
    rotulo, hoje = ("LinkedIn" if rede == "linkedin" else "X"), agora().date().isoformat()
    cab = (f"# Voice · {c['nome']} · {rotulo} · version {v + 1} · calibrated on {hoje}" if idioma() == "en"
           else f"# Voz · {c['nome']} · {rotulo} · versão {v + 1} · calibrada em {hoje}")
    voz_arq(pasta, rede).write_text(cab + "\n" + corpo.lstrip("\n") + "\n", encoding="utf-8")
    registrar(pasta, rede, "voz", versao=v + 1)
    out({"voz": str(voz_arq(pasta, rede)), "versao": v + 1})
    return 0


# --------------------------------------------------------------------------------------------
# Modo vigia (X): uma execução curta a cada 10 min pela tarefa do Windows, sem processo eterno
# --------------------------------------------------------------------------------------------
def extrair_json(texto):
    """O objeto JSON de uma resposta (tolera cerca de código e texto em volta)."""
    t = (texto or "").strip()
    ini, fim = t.find("{"), t.rfind("}")
    if ini < 0 or fim <= ini:
        raise Erro(f"o escritor não devolveu JSON: {t[:200]!r}", 2)
    try:
        dado = json.loads(t[ini:fim + 1])
    except ValueError as e:
        raise Erro(f"o JSON do escritor não abre: {e}", 2)
    if not isinstance(dado, dict):
        raise Erro("o escritor devolveu JSON que não é objeto", 2)
    return dado


MODO_CLAUDE = {"modo": None}           # qual jeito de chamar o Claude Code deu certo (o testar mostra)
SISTEMA_ESCRITOR = ("Você escreve comentários curtos para redes sociais seguindo à risca o pacote que recebe. "
                    "Responda só com o objeto JSON pedido.")


def escrever_com_claude(pacote, modelo="sonnet", timeout=300):
    """Pede ao Claude Code (o plano de quem opera) só o JSON dos comentários, sem nenhuma ferramenta.
    Enxuto: sem o prompt de sistema do Claude Code, sem plugins, hooks e MCP do PC e sem gravar a
    sessão; se o Claude Code do PC não aceitar isso, tenta de novo do jeito simples. Roda em
    Documentos\\Replai para não carregar o CLAUDE.md de nenhum projeto."""
    import subprocess
    exe = caminho_claude()
    if not exe:
        raise Erro("o Claude Code de linha de comando não está instalado: o vigia precisa dele "
                   "(rode o instalador do Replai e depois o login do vigia: referencias/configurar.md, passo 5)", 2)
    simples = [exe, "-p", "--model", modelo, "--output-format", "json", "--max-turns", "1",
               "--tools", "", "--disallowedTools", "mcp__*"]
    enxuto = simples + ["--system-prompt", SISTEMA_ESCRITOR, "--setting-sources", "local",
                        "--strict-mcp-config", "--no-session-persistence"]
    extra = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    BASE.mkdir(parents=True, exist_ok=True)
    for cmd in (enxuto, simples):
        try:
            p = subprocess.run(cmd, input=pacote, capture_output=True, text=True, encoding="utf-8",
                               timeout=timeout, cwd=str(BASE), **extra)
        except subprocess.TimeoutExpired:
            raise Erro("o Claude Code não respondeu a tempo", 2)
        try:
            dado = json.loads(p.stdout)
        except ValueError:
            dado = {"is_error": True, "result": (p.stderr or p.stdout or "").strip()}
        if p.returncode == 0 and not dado.get("is_error"):
            MODO_CLAUDE["modo"] = "enxuto" if cmd is enxuto else "simples"
            break
    texto = dado.get("result") or ""
    if p.returncode != 0 or dado.get("is_error"):
        raise Erro(f"o Claude Code falhou: {texto[:300]}", 2)
    return extrair_json(texto)


def vigiar_redes(pasta, c, partes, escritor, dormir=time.sleep):
    """Uma execução do vigia com o navegador aberto. `partes`: {rede: (coletar(cota), passos(fila))}.
    Coleta cada rede, escreve o que é novo nas redes numa chamada só ao escritor (nenhuma, sem post
    novo: zero token) e, nas redes em "sozinho", posta as duas ao mesmo tempo. {rede: resultado}"""
    res, prontas = {}, []
    for rede, (coletar, _passos) in partes.items():
        cota, motivo = cota_da_coleta(pasta, c, rede)
        if cota <= 0:
            res[rede] = {"nada_a_fazer": motivo}
            continue
        try:
            res[rede] = {"coleta": coletar(cota)}
        except Exception as e:  # noqa: BLE001
            res[rede] = erro_dict(erro_inesperado(e))
            continue
        if not res[rede]["coleta"].get("nada_a_fazer"):
            prontas.append(rede)
    if not prontas:
        return res
    try:
        for rede, esc in escrever_redes(pasta, c, prontas, escritor).items():
            res[rede].update(esc)
    except Erro as e:
        for rede in prontas:
            res[rede].update(erro_dict(e))
        return res
    passos = {}
    for rede in prontas:
        if rede_cfg(c, rede).get("modo") != "sozinho":
            res[rede]["revisao"] = "rascunhos esperando a revisão no chat"
            continue
        fila, cot = fila_para_postar(pasta, c, rede)
        if fila and (cot["comentarios"] > 0 or cot["curtidas"] > 0):
            try:
                passos[rede] = partes[rede][1](fila)
            except Exception as e:  # noqa: BLE001
                passos[rede] = {"parou": str(erro_inesperado(e)), "comentados": []}
    for rede, r in rodar_juntos(passos, dormir).items():
        res[rede]["postagem"] = r
    return res


def parte_x(pasta, c, leitor, page, acoes=None, rng=random, tocar=lambda: None):
    """(coletar, passos) do vigia do X: lê a Lista e as buscas (uma página quando não há nada novo)."""
    import x as X

    def passos(fila):
        meu = chave_perfil("x", c["redes"]["x"].get("perfil"))
        try:
            respondidos = X.respondidos(leitor.respostas_da_conta(meu), meu)
        except X.ErroX as e:
            if e.tipo != "LEITURA":            # leitura que o X mudou não é bloqueio: não para a rede
                registrar(pasta, "x", "parada", motivo=f"leitura: {e}")
            return {"parou": str(e), "comentados": []}
        return postar_x(pasta, c, fila, page, meu, respondidos, acoes=acoes, rng=rng, tocar=tocar, so_passos=True)
    return (lambda cota: coletar_x(pasta, c, cota, leitor, vigia=True)), passos


def vigiar_x(pasta, c, leitor, page, escritor, acoes=None, dormir=time.sleep, rng=random, tocar=lambda: None):
    return vigiar_redes(pasta, c, {"x": parte_x(pasta, c, leitor, page, acoes, rng, tocar)}, escritor, dormir)["x"]


def parte_linkedin(pasta, c, voy, page, avisos=None, acoes=None, rng=random, tocar=lambda: None):
    """(coletar, passos) do vigia do LinkedIn: lê a página de notificações (o sininho de cada perfil da
    lista) e só então os autores avisados. `avisos(page)` -> [{vanity, activity}] (o padrão é a tela)."""
    import linkedin as L
    avisos = avisos or L.posts_das_notificacoes

    def coletar(cota):
        perfis = perfis_da_rede(pasta, c, "linkedin")
        membros = {p["chave"] for p in perfis}
        lidos = [(a["vanity"], a["activity"]) for a in avisos(page) if a.get("vanity") in membros]
        if not lidos:
            return {"nada_a_fazer": "nenhum aviso novo de post de quem está na lista"}
        return coletar_linkedin(pasta, c, perfis, cota, voy, vigia=True, so_posts=lidos)

    def passos(fila):
        try:
            me = voy.me()
        except L.VoyagerErro as e:
            return {"parou": f"não consegui ler a conta logada: {e}", "comentados": []}
        return postar_linkedin(pasta, c, fila, page, voy, me, acoes=acoes, rng=rng, tocar=tocar, so_passos=True)
    return coletar, passos


def vigiar_linkedin(pasta, c, voy, page, escritor, avisos=None, acoes=None, dormir=time.sleep, rng=random,
                    tocar=lambda: None):
    return vigiar_redes(pasta, c, {"linkedin": parte_linkedin(pasta, c, voy, page, avisos, acoes, rng, tocar)},
                        escritor, dormir)["linkedin"]


def ligar_sininhos(pasta, c, page, acoes=None, dormir=time.sleep, rng=random, maximo=None):
    """Liga o sininho ("avisar todas as publicações") nos perfis da lista do LinkedIn que ainda não têm,
    até o teto do dia (e `maximo` por vez: o vigia liga uns poucos a cada execução), com pausa entre um
    e outro. Quem falhou hoje fica para amanhã. Para no primeiro sinal de bloqueio."""
    if acoes is None:
        import linkedin as acoes
    rede = "linkedin"
    cfg_v = R.VIGIA[rede]
    evs = eventos(pasta, rede)
    feitos = {e.get("autor") for e in evs if e.get("ev") == "sininho" and e.get("situacao") in ("ligado", "ja_estava")}
    hoje = agora().date().isoformat()
    de_hoje = [e for e in evs if e.get("ev") == "sininho" and e.get("quando", "").startswith(hoje)]
    usados, tentados = len(de_hoje), {e.get("autor") for e in de_hoje}
    faltam = [p for p in perfis_da_rede(pasta, c, rede) if p["chave"] not in feitos | tentados]
    if maximo is not None:
        faltam = faltam[:maximo]
    res = {"tentados": 0, "ligados": 0, "ja_estavam": 0, "sem_botao": [], "nao_confirmou": [], "parou": None,
           "faltam_depois": 0}
    for i, p in enumerate(faltam):
        if usados >= cfg_v["sininhos_por_dia"]:
            break
        res["tentados"] += 1
        url = p["perfil"] if str(p["perfil"]).startswith("http") else f"https://www.linkedin.com/in/{p['chave']}/"
        situacao, detalhe = acoes.ligar_sininho(page, url)
        usados += 1
        if situacao == "SESSAO":
            marcar_sessao(pasta, rede, False)
            res["parou"] = "a sessão do LinkedIn caiu: rode o login"
            break
        if situacao in ("CAPTCHA", "LIMIT"):
            registrar(pasta, rede, "parada", motivo=f"{situacao} ao ligar o sininho")
            res["parou"] = f"{situacao} do LinkedIn: rede parada até amanhã"
            break
        registrar(pasta, rede, "sininho", autor=p["chave"], situacao=situacao, detalhe=detalhe)
        if situacao == "ligado":
            res["ligados"] += 1
        elif situacao == "ja_estava":
            res["ja_estavam"] += 1
        else:
            res[situacao].append(f"{p['nome']}: {detalhe}")
        if i < len(faltam) - 1:
            dormir(rng.uniform(*cfg_v["pausa_sininho_s"]))
    feitos = {e.get("autor") for e in eventos(pasta, rede)
              if e.get("ev") == "sininho" and e.get("situacao") in ("ligado", "ja_estava")}
    res["faltam_depois"] = sum(1 for p in perfis_da_rede(pasta, c, rede) if p["chave"] not in feitos)
    return res


def cmd_sininho(args):
    pasta, c = carregar(args)
    if args.rede == "x":
        raise Erro("o sininho é só do LinkedIn (no X o vigia lê a Lista)")
    rede_cfg(c, "linkedin")
    from playwright.sync_api import sync_playwright
    with Trava(trava_de(pasta, c, "linkedin")), sync_playwright() as pw:
        ctx, page, _voy = abrir_rede(pasta, c, pw, "linkedin")
        try:
            res = ligar_sininhos(pasta, c, page)
        finally:
            fechar(ctx)
    out(res)
    return 4 if res.get("parou") else 0


def resumo_vigia(res):
    """Uma linha para o registro, o log e o status."""
    if res.get("erro"):
        return "erro: " + res["erro"][:160]
    if res.get("nada_a_fazer"):
        return "nada: " + str(res["nada_a_fazer"])
    col = res.get("coleta") or {}
    if col.get("nada_a_fazer"):
        return "nada: " + str(col["nada_a_fazer"])
    esc, post = res.get("escrita_1") or {}, res.get("postagem") or {}
    return (f"{col.get('posts_vistos', 0)} vistos, {col.get('candidatos', 0)} novos, "
            f"{col.get('no_atraso', 0)} no atraso, {esc.get('aceitos', 0)} escritos, "
            f"{len(post.get('comentados') or [])} respondidos"
            + (f", {res['sininhos']['ligados']} sininhos" if (res.get("sininhos") or {}).get("ligados") else "")
            + (f", PAROU: {post['parou']}" if post.get("parou") else ""))


def anotar_log(caminho, res, max_linhas=400):
    caminho = Path(caminho)
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.exists() else []
    linhas = (linhas + [f"{agora_iso()} {resumo_vigia(res)}"])[-max_linhas:]
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def vigia_na_hora(pasta, rede):
    """A tarefa roda a cada VIGIA_TICK_MIN; cada rede só age no intervalo dela (X 10 min, LinkedIn 15),
    com folga para a espera sorteada do começo."""
    ult = ultimo_vigia(pasta, rede)
    q = R.data_de((ult or {}).get("quando"))
    return q is None or agora() - q >= timedelta(minutes=R.VIGIA[rede]["intervalo_min"] - R.VIGIA_FOLGA_MIN)


def cmd_vigiar(args):
    """Uma execução do vigia. Com --todas (é o que a tarefa do PC chama a cada 5 min), passa pelas contas
    ligadas UMA DE CADA VEZ: nunca dois navegadores do Replai abertos juntos. Uma execução que ainda não
    terminou faz a seguinte pular (a trava do vigia)."""
    if not args.todas:
        pasta, c = carregar(args)
        return saida_redes(args.rede, vigiar_conta(pasta, c, args))
    res = {}
    try:
        with Trava(BASE / ".vigia.lock") as trava:
            for pasta in contas():
                try:
                    c = ler_conta(pasta)
                except Erro:
                    continue
                if not conta_ligada(c) or not any(rede_com_vigia(c, r) for r in R.REDES):
                    continue
                trava.tocar()
                try:
                    res[pasta] = vigiar_conta(pasta, c, args)
                except Erro as e:            # uma conta com problema não segura as outras
                    res[pasta] = erro_dict(e)
    except Erro as e:
        if e.codigo != 3:
            raise
        res = {"nada_a_fazer": "o vigia anterior ainda está rodando"}
    out(res)
    return 0


def vigiar_conta(pasta, c, args):
    """As redes da conta com vigia ligado e na hora delas, no mesmo navegador e com uma chamada só ao
    Claude. Sem nada a fazer, não abre o navegador. Anota no registro (evento 'vigia') e em
    vigia-<rede>.log. -> {rede: resultado}"""
    if args.rede:
        redes = redes_pedidas(c, args.rede)
    else:
        redes = [r for r in R.REDES if ((c.get("redes") or {}).get(r) or {}).get("ativa") and c["redes"][r].get("vigia")]
    res, vez = {}, []
    for rede in redes:
        cota, motivo = cota_da_coleta(pasta, c, rede)
        if cota <= 0:
            res[rede] = {"nada_a_fazer": motivo}
        elif args.agora or args.rede or vigia_na_hora(pasta, rede):
            vez.append(rede)
    if vez:
        if not args.agora and not args.todas:
            time.sleep(random.uniform(*R.VIGIA[vez[0]]["espera_inicial_s"]))
        from playwright.sync_api import sync_playwright
        try:
            with Trava(trava_de(pasta, c, vez[0])) as trava, sync_playwright() as pw:
                ctx, abertas, erros = abrir_redes(pasta, c, pw, vez, fora_da_tela=True)
                try:
                    res.update({r: erro_dict(e) for r, e in erros.items()})
                    partes = {r: (parte_x if r == "x" else parte_linkedin)(pasta, c, leitor, page, tocar=trava.tocar)
                              for r, (page, leitor) in abertas.items()}
                    res.update(vigiar_redes(pasta, c, partes, escrever_com_claude))
                    li = res.get("linkedin") or {}
                    if "linkedin" in abertas and "coleta" in li and not li.get("erro") \
                            and not (li.get("postagem") or {}).get("parou"):
                        s = ligar_sininhos(pasta, c, abertas["linkedin"][0],
                                           maximo=R.VIGIA["linkedin"]["sininhos_por_execucao"])
                        if s["tentados"]:
                            li["sininhos"] = s
                finally:
                    fechar(ctx)
        except Exception as e:  # noqa: BLE001 - o vigia sempre anota o que houve
            e = erro_inesperado(e)
            res.update({r: erro_dict(e) for r in vez if not (res.get(r) or {}).get("coleta")})
    for rede, r in res.items():
        registrar(pasta, rede, "vigia", resumo=resumo_vigia(r))
        anotar_log(arq(pasta, f"vigia-{rede}.log"), r)
    if any(r.get("escrita_1") or r.get("postagem") for r in res.values()):
        sincronizar_planilha(pasta, c)
    return res


TAREFA_VIGIA = "Replai vigia"     # uma tarefa só no PC, para todas as contas (desde 12/11/2026)


def comando_vigia(acao):
    """O comando do Agendador do Windows que liga ou desliga o vigia do PC (sem janela: pythonw)."""
    if acao == "desligar":
        return ["schtasks", "/delete", "/tn", TAREFA_VIGIA, "/f"]
    py = Path(sys.executable)
    exe = py.with_name("pythonw.exe") if py.with_name("pythonw.exe").exists() else py
    tr = f'"{exe}" "{SCRIPT}" vigiar --todas'
    return ["schtasks", "/create", "/tn", TAREFA_VIGIA, "/sc", "minute", "/mo", str(R.VIGIA_TICK_MIN), "/tr", tr, "/f"]


def comando_bateria():
    """O schtasks cria a tarefa "só na tomada" e não tem opção para isso: o PowerShell troca."""
    nome = TAREFA_VIGIA
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command",
            "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            f"-StartWhenAvailable; Set-ScheduledTask -TaskName '{nome}' -Settings $s | Out-Null"]


# No Mac o vigia é um agente do launchd do usuário: roda com a sessão aberta (a tela pode estar
# bloqueada), como a tarefa do Windows. O PATH do launchd é curto: vai junto o caminho do `claude`.
PASTA_AGENTES = Path.home() / "Library" / "LaunchAgents"
PATH_MAC = "~/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def rotulo_vigia(pasta=None):
    """O do PC; com `pasta`, o rótulo antigo (um agente por conta, até 12/11/2026), só para apagar."""
    if pasta is None:
        return "com.replai.vigia"
    return "com.replai.vigia." + re.sub(r"[^A-Za-z0-9]+", "-", R.sem_acento(str(pasta))).strip("-").lower()


def plist_do_vigia():
    """O agente do launchd que chama `vigiar --todas` a cada VIGIA_TICK_MIN minutos."""
    return {"Label": rotulo_vigia(),
            "ProgramArguments": [sys.executable, str(SCRIPT), "vigiar", "--todas"],
            "StartInterval": R.VIGIA_TICK_MIN * 60, "RunAtLoad": False,
            "EnvironmentVariables": {"PATH": ":".join(os.path.expanduser(p) for p in PATH_MAC.split(":"))},
            "StandardOutPath": "/dev/null", "StandardErrorPath": "/dev/null"}


def _sistema(sistema=None):
    return sistema or ("windows" if os.name == "nt" else "mac" if MAC else "outro")


def tarefa_do_vigia(acao, sistema=None):
    """(código, saída) de ligar, desligar ou consultar o agendamento do vigia do PC: a tarefa do Windows
    ou o agente do launchd no Mac."""
    sistema = _sistema(sistema)
    if sistema == "windows":
        if acao == "consultar":
            return rodar_comando(["schtasks", "/query", "/tn", TAREFA_VIGIA])
        cod, saida = rodar_comando(comando_vigia(acao))
        if acao == "ligar" and cod == 0:
            rodar_comando(comando_bateria())   # sem isto, notebook na bateria não roda o vigia
        return cod, saida
    if sistema != "mac":
        return 1, "o vigia roda no Windows e no Mac"
    import plistlib
    dominio = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui/501"
    arquivo = PASTA_AGENTES / f"{rotulo_vigia()}.plist"
    if acao == "consultar":
        return rodar_comando(["launchctl", "print", f"{dominio}/{rotulo_vigia()}"])
    rodar_comando(["launchctl", "bootout", dominio, str(arquivo)])      # tira o antigo, se houver
    if acao == "desligar":
        arquivo.unlink(missing_ok=True)
        return 0, ""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_bytes(plistlib.dumps(plist_do_vigia()))
    return rodar_comando(["launchctl", "bootstrap", dominio, str(arquivo)])


def apagar_vigia_antigo(pasta, sistema=None):
    """Até 12/11/2026 era um agendamento por conta (e, antes de 27/10, um por rede): com várias contas
    no PC, isso abria vários navegadores juntos. Some com o antigo desta conta."""
    sistema = _sistema(sistema)
    if sistema == "windows":
        for nome in [f"Replai vigia {pasta}", *(f"Replai vigia {r} {pasta}" for r in R.REDES)]:
            rodar_comando(["schtasks", "/delete", "/tn", nome, "/f"])
    elif sistema == "mac":
        dominio = f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui/501"
        antigo = PASTA_AGENTES / f"{rotulo_vigia(pasta)}.plist"
        if antigo.exists():
            rodar_comando(["launchctl", "bootout", dominio, str(antigo)])
            antigo.unlink(missing_ok=True)


def acertar_tarefa_do_vigia(sistema=None):
    """Liga a tarefa do PC se alguma conta ligada tem vigia; senão, desliga. (código, saída, ligada)"""
    alguma = False
    for pasta in contas():
        try:
            c = ler_conta(pasta)
        except Erro:
            continue
        if conta_ligada(c) and any(rede_com_vigia(c, r) for r in R.REDES):
            alguma = True
            break
    cod, saida = tarefa_do_vigia("ligar" if alguma else "desligar", sistema)
    return cod, saida, alguma


def cmd_vigia(args):
    """Liga ou desliga o vigia (sem --rede, nas redes ligadas). Um agendamento por conta (tarefa do
    Windows ou agente do launchd no Mac); ele fica enquanto alguma rede tiver o vigia ligado."""
    pasta, c = carregar(args)
    redes = redes_pedidas(c, args.rede)
    if not (args.ligar or args.desligar):
        est = {r: {"vigia": bool(rede_cfg(c, r).get("vigia")), "ultimo": ultimo_vigia(pasta, r)} for r in redes}
        out(est[args.rede] if args.rede else est)
        return 0
    if args.ligar and not claude_instalado():
        raise Erro("o vigia precisa do Claude Code de linha de comando: rode o instalador do Replai e "
                   "depois o login do vigia (referencias/configurar.md, passo 5)")
    for r in redes:
        rede_cfg(c, r)["vigia"] = bool(args.ligar)
    com_vigia = [r for r in R.REDES if rede_com_vigia(c, r)]
    gravar_conta(pasta, c)
    apagar_vigia_antigo(pasta)
    cod, saida, ligada = acertar_tarefa_do_vigia()
    if cod != 0 and ligada:
        raise Erro(f"o agendador do sistema recusou o vigia: {saida[:200]}")
    out({"vigia": bool(args.ligar), "redes": redes, "redes_com_vigia": com_vigia,
         "a_cada_min": {r: R.VIGIA[r]["intervalo_min"] for r in com_vigia}})
    return 0


def caminho_claude():
    """O `claude` do PATH ou, quando o PATH não tem, onde os instaladores põem: ~/.local/bin (o oficial,
    Mac e Windows) e a pasta de pacotes do winget (que às vezes não cria o atalho no PATH)."""
    import shutil
    achado = shutil.which("claude")
    if achado:
        return achado
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet"
    candidatos = [Path.home() / ".local" / "bin" / "claude", Path.home() / ".local" / "bin" / "claude.exe",
                  winget / "Links" / "claude.exe", *sorted(winget.glob("Packages/Anthropic.ClaudeCode_*/claude.exe"))]
    return next((str(p) for p in candidatos if p.is_file()), None)


def claude_instalado():
    return bool(caminho_claude())


def rodar_comando(cmd):
    """(código, saída) de um comando do sistema (schtasks, launchctl); separado para os testes trocarem."""
    import subprocess
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        return 1, str(e)
    return p.returncode, (p.stderr or p.stdout or "").strip()


def ultimo_vigia(pasta, rede):
    ult = None
    for e in eventos(pasta, rede):
        if e.get("ev") == "vigia":
            ult = {"quando": e.get("quando"), "resumo": e.get("resumo")}
    return ult


# --------------------------------------------------------------------------------------------
# Entrada
# --------------------------------------------------------------------------------------------
# Os comandos que abrem o navegador do robô rodam numa área de trabalho escondida do Windows: um navegador
# de verdade (as redes desconfiam do headless), mas sem janela na tela, na barra de tarefas ou roubando o
# foco de quem usa o PC. O robô digita e rola pelo protocolo do navegador, sem teclado nem mouse do PC.
# O login fica fora: nele quem digita é a pessoa. REPLAI_VISIVEL=1 mostra o robô (para investigar).
COM_ROBO = {"coletar", "postar", "vigiar", "testar", "voz-amostra", "sininho", "calibrar"}
AREA_ESCONDIDA = "ReplaiEscondido"
ESCONDIDO_MAX_SEG = LOCK_VALIDADE_SEG          # o mesmo teto da trava (3 h)


def rodar_escondido(argv):
    """Roda este mesmo comando num processo filho na área escondida e devolve o código dele (a saída
    vem por arquivo). None se o Windows recusar: aí o comando roda aqui mesmo, como antes."""
    import ctypes
    import ctypes.wintypes as W
    import subprocess
    import tempfile

    class STARTUPINFOW(ctypes.Structure):
        _fields_ = [("cb", W.DWORD), ("lpReserved", W.LPWSTR), ("lpDesktop", W.LPWSTR), ("lpTitle", W.LPWSTR),
                    ("dwX", W.DWORD), ("dwY", W.DWORD), ("dwXSize", W.DWORD), ("dwYSize", W.DWORD),
                    ("dwXCountChars", W.DWORD), ("dwYCountChars", W.DWORD), ("dwFillAttribute", W.DWORD),
                    ("dwFlags", W.DWORD), ("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                    ("lpReserved2", ctypes.c_void_p), ("hStdInput", W.HANDLE), ("hStdOutput", W.HANDLE),
                    ("hStdError", W.HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE), ("dwProcessId", W.DWORD),
                    ("dwThreadId", W.DWORD)]

    k32, u32 = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("user32", use_last_error=True)
    u32.CreateDesktopW.restype = W.HANDLE
    u32.CreateDesktopW.argtypes = [W.LPCWSTR, W.LPCWSTR, ctypes.c_void_p, W.DWORD, W.DWORD, ctypes.c_void_p]
    area = u32.CreateDesktopW(AREA_ESCONDIDA, None, None, 0, 0x10000000, None)   # GENERIC_ALL
    if not area:
        return None
    fd, saida = tempfile.mkstemp(prefix="replai-", suffix=".txt")
    os.close(fd)
    os.environ.update(REPLAI_ESCONDIDO="1", REPLAI_SAIDA=saida)   # o filho herda o ambiente
    si = STARTUPINFOW(cb=ctypes.sizeof(STARTUPINFOW), lpDesktop=AREA_ESCONDIDA)
    pi = PROCESS_INFORMATION()
    linha = ctypes.create_unicode_buffer(subprocess.list2cmdline([sys.executable, str(SCRIPT), *argv]))
    try:
        if not k32.CreateProcessW(None, linha, None, None, False, 0x08000000, None, None,   # sem console
                                  ctypes.byref(si), ctypes.byref(pi)):
            return None
        # ponytail: teto fixo igual ao da trava; nenhum comando legítimo chega perto (rodada: 45 min).
        travou = k32.WaitForSingleObject(pi.hProcess, ESCONDIDO_MAX_SEG * 1000) == 0x102   # WAIT_TIMEOUT
        if travou:                       # filho preso (página que não responde): não segura o vigia
            k32.TerminateProcess(pi.hProcess, 2)
            k32.WaitForSingleObject(pi.hProcess, 10000)
        cod = W.DWORD()
        k32.GetExitCodeProcess(pi.hProcess, ctypes.byref(cod))
        k32.CloseHandle(pi.hProcess)
        k32.CloseHandle(pi.hThread)
        texto = Path(saida).read_text(encoding="utf-8").strip()
        if travou:
            texto = json.dumps({"erro": f"o comando travou e foi encerrado depois de {ESCONDIDO_MAX_SEG // 60} "
                                        "minutos", "codigo": 2}, ensure_ascii=False)
        if texto:
            print(texto, flush=True)
        return 2 if travou else cod.value
    finally:
        for k in ("REPLAI_ESCONDIDO", "REPLAI_SAIDA"):
            os.environ.pop(k, None)
        u32.CloseDesktop(W.HANDLE(area))
        try:
            os.unlink(saida)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(prog="replai.py")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def novo(nome, rede=False, rede_obrigatoria=True):
        p = sub.add_parser(nome)
        p.add_argument("--conta")
        if rede:
            p.add_argument("--rede", choices=R.REDES, required=rede_obrigatoria)
        return p

    novo("checar")
    p = novo("configurar")
    p.add_argument("--operador")
    p.add_argument("--idioma", choices=("pt", "en"))
    p.add_argument("--nome", required=True)
    p.add_argument("--redes", default="linkedin,x")
    p.add_argument("--lista")
    p.add_argument("--x-lista")
    p.add_argument("--perfil-linkedin")
    p.add_argument("--perfil-x")
    p.add_argument("--nunca-citar", action="append")
    p.add_argument("--pode-citar", action="append")
    p = novo("operador")
    p.add_argument("--nome")
    p.add_argument("--idioma", choices=("pt", "en"))
    p = novo("login", rede=True, rede_obrigatoria=False)
    p.add_argument("--fechar", action="store_true")   # a skill fecha a janela quando a pessoa avisa que logou
    p = novo("conta", rede=True, rede_obrigatoria=False)
    p.add_argument("--nome")
    p.add_argument("--ativa", choices=("sim", "nao"))
    p.add_argument("--modo", choices=("revisao", "sozinho"))
    p.add_argument("--perfil")
    p.add_argument("--teto-comentarios", type=int)
    p.add_argument("--teto-curtidas", type=int)
    p.add_argument("--ignorar-proibida")
    p.add_argument("--nunca-citar")
    p.add_argument("--pode-citar")
    p = novo("lista", rede=True, rede_obrigatoria=False)
    p.add_argument("--nome", required=True)
    p.add_argument("--csv", nargs="?", const="")   # sem caminho: Documentos/Replai/<Conta>/lista.csv
    p.add_argument("--excel")
    p.add_argument("--x-lista")
    p.add_argument("--planilha")
    p.add_argument("--prioridade", choices=("alta", "normal"))
    p.add_argument("--ativa", choices=("sim", "nao"))
    p = novo("perfil")
    p.add_argument("--lista")
    acao = p.add_mutually_exclusive_group(required=True)
    acao.add_argument("--adicionar", nargs="+", metavar="LINK_OU_@")
    acao.add_argument("--tirar")
    acao.add_argument("--pausar")
    acao.add_argument("--retomar")
    acao.add_argument("--listar", nargs="?", const=True)
    p.add_argument("--nome")
    p.add_argument("--prioridade", choices=("alta", "normal"))
    p.add_argument("--obs")
    p = novo("coletar", rede=True, rede_obrigatoria=False)
    p.add_argument("--lista")
    p.add_argument("--simular", action="store_true")
    p.add_argument("--max", type=int)
    novo("lote", rede=True, rede_obrigatoria=False)
    novo("escrever", rede=True, rede_obrigatoria=False).add_argument("--arquivo", required=True)
    novo("revisao", rede=True, rede_obrigatoria=False)
    novo("aprovar", rede=True, rede_obrigatoria=False).add_argument("--arquivo", required=True)
    p = novo("postar", rede=True, rede_obrigatoria=False)
    p.add_argument("--so")
    p.add_argument("--simular", action="store_true")
    novo("status")
    novo("liberar", rede=True).add_argument("--motivo")
    novo("calibrar", rede=True)
    novo("testar", rede=True, rede_obrigatoria=False)
    novo("voz-amostra", rede=True, rede_obrigatoria=False)
    novo("material").add_argument("--arquivo", action="append", required=True)
    novo("copia")
    novo("atualizacao").add_argument("--aplicar", action="store_true")
    p = novo("restaurar")
    p.add_argument("--arquivo")
    p.add_argument("--substituir", action="store_true")
    novo("voz-pacote", rede=True, rede_obrigatoria=False).add_argument("--tipo", choices=("retrato", "aprendizado"), required=True)
    novo("voz", rede=True).add_argument("--arquivo", required=True)
    p = novo("vigiar", rede=True, rede_obrigatoria=False)
    p.add_argument("--agora", action="store_true")
    p.add_argument("--todas", action="store_true")     # o que a tarefa do PC chama: as contas, uma por vez
    novo("contas")
    novo("sininho", rede=True, rede_obrigatoria=False)
    g = novo("vigia", rede=True, rede_obrigatoria=False).add_mutually_exclusive_group()
    g.add_argument("--ligar", action="store_true")
    g.add_argument("--desligar", action="store_true")
    args = ap.parse_args(argv)
    if args.cmd in COM_ROBO and os.name == "nt" and not os.environ.get("REPLAI_ESCONDIDO") \
            and not os.environ.get("REPLAI_VISIVEL"):
        cod = rodar_escondido(sys.argv[1:] if argv is None else list(argv))
        if cod is not None:
            return cod
    if os.environ.get("REPLAI_SAIDA"):          # filho na área escondida: a saída vai para o pai por arquivo
        sys.stdout = open(os.environ["REPLAI_SAIDA"], "w", encoding="utf-8")
    fn = globals().get("cmd_" + args.cmd.replace("-", "_"))
    try:
        if not fn:
            raise Erro(f"o comando {args.cmd} ainda não existe nesta versão")
        return fn(args) or 0
    except Exception as e:  # noqa: BLE001 - nunca sai sem dizer o quê (no vigia escondido não há console)
        e = erro_inesperado(e)
        out({"erro": str(e), "codigo": e.codigo})
        return e.codigo


if __name__ == "__main__":
    sys.exit(main())
