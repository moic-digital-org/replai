"""A lista de perfis da conta num CSV local (Documentos\\Replai\\<Conta>\\lista.csv): a fonte da verdade.

Um arquivo serve às duas redes (uma coluna para o LinkedIn, outra para o X), abre no Excel (separador
';' e UTF-8 com BOM, que o Excel em português lê certo) e é relido a cada rodada. Quem opera edita no
Excel ou pede ao Claude, que usa o comando `perfil` (adicionar, tirar, pausar, retomar, listar).

Funções puras sobre listas de dicts, mais `ler`/`gravar`. Sem dependência do resto do Replai."""
import csv
import io
import os
import re
import unicodedata
from pathlib import Path

COLUNAS = ["Nome", "LinkedIn", "X", "Prioridade", "Incluir", "Observação"]
NAO = ("não", "nao", "n", "no", "0", "false")

# cabeçalhos que a pessoa pode ter escrito à mão (ou em inglês) -> a coluna padrão
_ALIAS = {"nome": "Nome", "name": "Nome", "nome completo": "Nome", "full name": "Nome",
          "linkedin": "LinkedIn", "perfil no linkedin": "LinkedIn", "linkedin url": "LinkedIn",
          "x": "X", "twitter": "X", "@": "X", "x handle": "X", "perfil no x": "X", "@ no x": "X",
          "prioridade": "Prioridade", "priority": "Prioridade", "incluir": "Incluir", "include": "Incluir",
          "observação": "Observação", "observacao": "Observação", "obs": "Observação", "notes": "Observação"}


class ArquivoAberto(Exception):
    """O Excel trava o CSV enquanto ele está aberto: nada foi gravado."""


def sem_acento(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s or "") if unicodedata.category(ch) != "Mn")


def _norm_nome(s):
    return " ".join(sem_acento(s).casefold().split())


def chave_perfil(rede, perfil):
    """A identidade do perfil numa rede: a vanity no LinkedIn, o @ (sem @) no X. Minúsculas."""
    p = (perfil or "").strip()
    if rede == "linkedin":
        from urllib.parse import unquote
        m = re.search(r"linkedin\.com/in/([^/?#]+)", p, re.I)
        return unquote(m.group(1)).strip("/").lower() if m else ""
    m = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]{1,15})", p, re.I)
    h = m.group(1) if m else p.lstrip("@")
    return h.lower() if re.fullmatch(r"[A-Za-z0-9_]{1,15}", h or "") else ""


def classificar(valor):
    """O que a pessoa mandou -> (rede, valor normalizado) ou None. Link do LinkedIn -> linkedin; link do
    X/Twitter ou @handle -> x. Um nome solto não é perfil."""
    v = (valor or "").strip()
    k = chave_perfil("linkedin", v)
    if k:
        return "linkedin", f"https://www.linkedin.com/in/{k}/"
    if re.search(r"(x|twitter)\.com/", v, re.I) or v.startswith("@"):
        k = chave_perfil("x", v)
        if k:
            return "x", "@" + k
    return None


def ler_texto(texto):
    """Texto do CSV -> [dict com as COLUNAS]. Aceita ',' ';' ou tab e cabeçalhos com outros nomes."""
    if not (texto or "").strip():
        return []
    try:
        delim = csv.Sniffer().sniff(texto[:4096], delimiters=",;\t").delimiter
    except csv.Error:
        cab = texto.split("\n", 1)[0]
        delim = ";" if cab.count(";") >= cab.count(",") else ","
    linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    if not linhas:
        return []
    cab = [_ALIAS.get(str(x).strip().lower(), str(x).strip()) for x in linhas[0]]
    saida = []
    for r in linhas[1:]:
        d = {c: "" for c in COLUNAS}
        for i, col in enumerate(cab):
            if i < len(r) and col:
                d[col] = (r[i] or "").strip()
        if any(d.get(c) for c in ("Nome", "LinkedIn", "X")):
            saida.append(d)
    return saida


def ler(caminho):
    p = Path(caminho)
    if not p.exists():
        return []
    return ler_texto(p.read_text(encoding="utf-8-sig"))


def texto_csv(linhas):
    buf = io.StringIO()
    extras = [k for ln in linhas for k in ln if k not in COLUNAS]
    cols = COLUNAS + sorted(set(extras), key=extras.index)
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(cols)
    for ln in linhas:
        w.writerow([ln.get(c, "") for c in cols])
    return buf.getvalue()


def gravar(caminho, linhas):
    """Grava inteiro (arquivo temporário + troca), para um erro no meio nunca deixar a lista pela metade."""
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(texto_csv(linhas), encoding="utf-8-sig", newline="")
    try:
        os.replace(tmp, p)
    except PermissionError:
        tmp.unlink(missing_ok=True)
        raise ArquivoAberto(str(p))


def achar(linhas, alvo):
    """Índice da linha do `alvo` (link do LinkedIn, link do X, @ ou o nome), ou None. Ambíguo por nome
    (duas pessoas com o mesmo nome) também é None: melhor pedir o link do que mexer na pessoa errada."""
    c = classificar(alvo)
    if c:
        rede, _v = c
        k = chave_perfil(rede, alvo)
        col = "LinkedIn" if rede == "linkedin" else "X"
        for i, ln in enumerate(linhas):
            if chave_perfil(rede, ln.get(col)) == k:
                return i
        return None
    n = _norm_nome(alvo)
    achados = [i for i, ln in enumerate(linhas) if n and _norm_nome(ln.get("Nome")) == n]
    return achados[0] if len(achados) == 1 else None


def adicionar(linhas, perfis, nome="", prioridade="", obs=""):
    """Põe a pessoa na lista (ou completa a linha dela). `perfis`: links/@ de uma ou das duas redes.
    Casa com a linha existente pelo perfil de qualquer rede ou pelo nome. -> (linhas, 'nova'|'atualizada')."""
    achados = {}
    for v in perfis:
        c = classificar(v)
        if not c:
            raise ValueError(f"não reconheci como perfil do LinkedIn ou do X: {v}")
        achados[c[0]] = c[1]
    if not achados:
        raise ValueError("falta o link do LinkedIn ou o @ do X")
    linhas = [dict(ln) for ln in linhas]
    i = next((achar(linhas, v) for v in achados.values() if achar(linhas, v) is not None), None)
    if i is None and nome:
        i = achar(linhas, nome)
        if i is not None:   # mesmo nome mas outro perfil na mesma rede: é outra pessoa
            ln = linhas[i]
            for rede, v in achados.items():
                col = "LinkedIn" if rede == "linkedin" else "X"
                if ln.get(col) and chave_perfil(rede, ln[col]) != chave_perfil(rede, v):
                    i = None
                    break
    novo = i is None
    if novo:
        linhas.append({c: "" for c in COLUNAS} | {"Incluir": "Sim", "Prioridade": "normal"})
        i = len(linhas) - 1
    ln = linhas[i]
    for rede, v in achados.items():
        ln["LinkedIn" if rede == "linkedin" else "X"] = v
    if nome:
        ln["Nome"] = nome
    if prioridade:
        ln["Prioridade"] = prioridade
    if obs:
        ln["Observação"] = obs
    if novo:
        ln["Incluir"] = "Sim"
    return linhas, ("nova" if novo else "atualizada")


def tirar(linhas, alvo):
    i = achar(linhas, alvo)
    if i is None:
        raise LookupError(alvo)
    linhas = [dict(ln) for ln in linhas]
    return linhas, linhas.pop(i)


def incluir(linhas, alvo, sim):
    """Pausa (sim=False) ou retoma (sim=True) sem apagar a linha."""
    i = achar(linhas, alvo)
    if i is None:
        raise LookupError(alvo)
    linhas = [dict(ln) for ln in linhas]
    linhas[i]["Incluir"] = "Sim" if sim else "Não"
    return linhas, linhas[i]


def ativa(ln):
    return (ln.get("Incluir") or "Sim").strip().lower() not in NAO


def juntar(por_rede):
    """{rede: [{Nome, Perfil, Prioridade, Incluir, Observação}]} (de listas antigas) -> linhas do CSV,
    uma por pessoa: casa pelo nome quando a pessoa está nas duas redes."""
    linhas = []
    for rede, itens in por_rede.items():
        col = "LinkedIn" if rede == "linkedin" else "X"
        for d in itens:
            c = classificar(d.get("Perfil"))
            if not c or c[0] != rede:
                continue
            if any(chave_perfil(rede, ln.get(col)) == chave_perfil(rede, c[1]) for ln in linhas):
                continue
            n = _norm_nome(d.get("Nome"))
            alvo = next((ln for ln in linhas if n and _norm_nome(ln["Nome"]) == n and not ln.get(col)), None)
            if alvo is None:
                alvo = {c2: "" for c2 in COLUNAS} | {"Nome": d.get("Nome", ""), "Incluir": "Sim",
                                                     "Prioridade": "normal"}
                linhas.append(alvo)
            alvo[col] = c[1]
            if (d.get("Prioridade") or "").strip().lower() == "alta":
                alvo["Prioridade"] = "alta"
            if (d.get("Incluir") or "Sim").strip().lower() in NAO:
                alvo["Incluir"] = "Não"
            if d.get("Observação") and not alvo.get("Observação"):
                alvo["Observação"] = d["Observação"]
    return linhas
