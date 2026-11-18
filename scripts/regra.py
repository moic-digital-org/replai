#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · REGRAS puras: sem navegador, sem arquivo, sem rede.
"""Tudo o que o Replai decide e dá para provar sem abrir nada:

  1. o comentário pode sair? (`validar`)
  2. qual post entra na rodada? (`estados`, `selecionar`; a regra nº 1 mora aqui)
  3. quanto ainda cabe e em que ritmo? (`cotas`, `pausa`, `no_horario`)
  4. o que a revisão ensinou? (`proibidas_aprendidas`, `propor_sozinho`)

Testes: python regra_test.py
"""
import difflib
import hashlib
import math
import random
import re
import unicodedata
from datetime import datetime, timedelta, timezone

# O fuso do PC de quem opera. As regras usam o fuso do `agora` que recebem; este só vale para data
# gravada sem fuso.
FUSO = datetime.now().astimezone().tzinfo
REDES = ("linkedin", "x")


def sem_acento(s):
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def tokens(texto):
    """Palavras normalizadas: minúsculas, sem acento, apóstrofo reto."""
    t = sem_acento((texto or "").replace("\u2019", "'").lower())
    return re.findall(r"[a-z0-9']+", t)


def abertura(texto, n=3):
    """As n primeiras palavras normalizadas (a régua de 'mesma abertura')."""
    return " ".join(tokens(texto)[:n])


def data_de(s):
    """ISO (com Z, offset ou sem fuso) -> datetime com fuso; sem fuso vale o do PC. None se ilegível."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=FUSO)


# ============================================================================
# 1. O comentário pode sair?
# ============================================================================
MAX_CHARS, MIN_CHARS, MAX_PERGUNTAS, NGRAM = 280, 25, 1, 5

_RE_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
_RE_LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(com|io|xyz|org|net|co|ai|app|finance)(/|\b)", re.I)
_RE_PLACEHOLDER = re.compile(r"\{[^}]*\}|\[[^\]]*\]|\b(first|last|company)[_\s-]?name\b", re.I)
# Travessão, traço longo, setas e aspas duplas curvas: nunca são de gente digitando um comentário.
UNICODE_IA = ("\u2014", "\u2013", "\u2192", "\u21d2", "\u279c", "\u2794", "\u201c", "\u201d")

PITCH = [
    r"\blet'?s (connect|chat|talk|hop on|jump on|catch up)\b",
    r"\bhappy to (chat|connect|help|share)\b",
    r"\b(dm|message) me\b", r"\bsend me a (dm|message)\b", r"\bbook a\b", r"\bschedule a\b",
    r"\bcalendly\b", r"\bwe (help|can help|work with|offer|build)\b",
    r"\bour (team|company|agency|product|services?)\b",
    r"\bvamos conversar\b", r"\bposso ajudar\b", r"\bpodemos ajudar\b",
    r"\bnossa (empresa|ag[eê]ncia|equipe)\b", r"\bnosso (time|produto|servi[cç]o)\b",
    r"\bme chama\b", r"\bagendar\b", r"\bbora conversar\b",
    r"\bhablemos\b", r"\bpodemos ayudar\b", r"\bnuestra (empresa|agencia)\b", r"\bescr[ií]beme\b",
]

ELOGIO_VAZIO = [
    r"\bgreat post\b", r"\bgreat point\b", r"\blove this\b", r"\bloved this\b",
    r"\bthanks for sharing\b", r"\bthank you for sharing\b", r"\bwell said\b", r"\bso true\b",
    r"\bcouldn'?t agree more\b", r"\bexcellent (post|point)\b", r"\binteresting (post|read)\b",
    r"\bgreat read\b", r"\bspot[- ]on\b", r"\bgreat (insights?|share|perspective|take|article)\b",
    r"\b(absolutely|totally|completely) agree\b", r"\b(this|that) (really )?resonates\b",
    r"\bsuch an? (powerful|great|important|timely) (reminder|point|post|read)\b",
    r"\b(so|very|really) insightful\b", r"\binsightful (post|read|piece|take)\b",
    r"\b[oó]tim[oa] (post|ponto|reflex[aã]o|an[aá]lise|coloca[cç][aã]o|texto)\b",
    r"\bexcelente (post|ponto|reflex[aã]o|an[aá]lise|coloca[cç][aã]o|texto|provoca[cç][aã]o)\b",
    r"\bconcordo (plenamente|totalmente|com tudo|demais)\b", r"\bque reflex[aã]o\b",
    r"\breflex[aã]o (incr[ií]vel|necess[aá]ria|poderosa|valiosa|important[ií]ssima)\b",
    r"^(sem d[uú]vida|exatamente|perfeito|com certeza)[,.!]", r"\badorei\b", r"\bmuito bom\b",
    r"\bobrigad[oa] por compartilhar\b", r"\bparab[eé]ns\b", r"\bsensacional\b",
    r"\bgran post\b", r"\bexcelente punto\b", r"\bgracias por compartir\b", r"\bmuy bueno\b",
]

# Antítese de efeito nas três línguas. As EN são as de alta precisão (com a exceção da
# condicional educada "isn't X, it's fine"); PT/ES são a forma "não é X, é Y" com vírgula ou ponto
# (fora "não é à toa" e "não é por acaso"), "não é sobre" e "não é um problema de X, mas de Y".
ANTITESE = [
    r"\bnot just\b", r"\bnot only\b", r"\bisn'?t just\b", r"\bwasn'?t just\b",
    r"\bdoesn'?t just\b", r"\bmore than just\b",
    r"\b(it'?s|it is|this is) not about\b", r"\bisn'?t about\b",
    r"\bless \w+, more \w+\b",
    r"\bisn'?t [\w' ]{1,28}, it'?s (?!(?:completely |totally |all |perfectly )?"
    r"(?:fine|ok|okay|good|cool|no problem|all right|alright)\b)",
    r"\bit'?s not [\w' ]{1,28}, it'?s\b",
    r"\b(don'?t|doesn'?t) have a [\w' ]{1,28} problem\b",
    r"\bn[aã]o [eé] (?![àa] toa\b|por acaso\b)[^,.;?!]{1,30}[,;.] [eé]\b", r"\bn[aã]o [eé] (s[oó] )?sobre\b",
    r"\bn[aã]o [eé] (um|uma) (problema|quest[aã]o|tema) de [^,.;?!]{1,30},? (mas|e sim) de\b",
    r"\bn[aã]o se trata de\b", r"\bmenos \w+, mais \w+\b",
    r"\bno es [^,.;?!]{1,30}[,;] es\b", r"\bno se trata de\b", r"\bmenos \w+, m[aá]s \w+\b",
]

TELLS = [
    r"\bvale (notar|destacar|ressaltar|lembrar)\b", r"\b[eé] importante (notar|perceber|destacar)\b",
    r"\bcuriosamente\b", r"\balavanc(ar|ando)\b", r"\bpotencializ(ar|ando)\b", r"\btape[cç]aria\b",
    r"\bpanorama\b", r"\bparadigma\b", r"\ba verdade [eé]\b", r"\bpulo do gato\b",
    r"\bimagine um mundo\b", r"\bpense nisso como\b", r"\bcabe destacar\b",
    r"\b[eé] aqui que fica interessante\b", r"\bno fim do dia\b",
    r"\bvale la pena (notar|destacar)\b", r"\bes importante (notar|destacar)\b",
    r"\bhere'?s the (thing|kicker|catch)\b", r"\bthe truth is\b", r"\bit'?s worth noting\b",
    r"\binterestingly\b", r"\bnotably\b", r"\bimagine a world\b", r"\bthink of it as\b",
    r"\bgame[- ]?changer\b", r"\bat the end of the day\b", r"\bin today'?s\b",
    r"\bquietly\b", r"\bcaught my eye\b", r"\bstuck with me\b", r"\bmade me wonder\b",
    r"\bcongrats on\b", r"\bi went looking\b",
    r"\bcrucial\b", r"\bdivisor de [aá]guas\b", r"\bnesse sentido\b", r"\bpivotal\b",
]

# Léxico de IA: um isolado passa, o acúmulo (2+) reprova (regra da casa).
LEXICO_IA = [
    r"delve", r"utilize", r"robust", r"streamline", r"harness", r"seamless", r"tapestry",
    r"landscape", r"paradigm", r"realm", r"(?<!buyer )(?<!user )(?<!customer )journey",
    r"leverage", r"leveraging", r"navigate", r"navigating",
    r"deeply", r"fundamentally", r"remarkably", r"arguably",
    r"robust[oa]s?", r"otimizar", r"fundamentalmente", r"profundamente",
]
TIQUES = {"actually": 1, "basically": 1, "literalmente": 1}


def _ngrams(texto, n=NGRAM):
    tk = tokens(texto)
    return {" ".join(tk[i:i + n]) for i in range(len(tk) - n + 1)}


def validar(texto, recentes=(), proibidas=(), emoji_ok=False, aberturas=(), nomes=()):
    """Motivos para NÃO sair (lista vazia = pode sair). O Python barra a superfície; se o comentário
    agrega valor, se o fato é verdadeiro e se o idioma é o do post ficam com o escritor.

    `recentes`: comentários da conta (corpus): 5 palavras seguidas em comum reprova.
    `proibidas`: palavras que a revisão proibiu para a conta.
    `aberturas`: as 3 primeiras palavras (já normalizadas) de comentários recentes.
    `nomes`: o que a conta nunca cita (a empresa dela e os clientes)."""
    t = (texto or "").strip()
    if not t:
        return ["comentário vazio"]
    low = t.lower()
    motivos = []
    if "\n" in t or "\r" in t:
        motivos.append("tem quebra de linha: comentário é um parágrafo só")
    if len(t) > MAX_CHARS:
        motivos.append(f"{len(t)} caracteres; o teto é {MAX_CHARS}")
    if len(t) < MIN_CHARS:
        motivos.append(f"{len(t)} caracteres: curto demais (mínimo {MIN_CHARS})")
    if "#" in t:
        motivos.append("tem hashtag (#)")
    if "@" in t:
        motivos.append("tem @ (marca alguém sem querer)")
    if _RE_LINK.search(t):
        motivos.append("tem link ou domínio")
    if t.count("?") > MAX_PERGUNTAS:
        motivos.append(f"{t.count('?')} perguntas; no máximo {MAX_PERGUNTAS}")
    n_emoji = len(_RE_EMOJI.findall(t))
    if n_emoji > (1 if emoji_ok else 0):
        motivos.append(f"{n_emoji} emoji(s); a voz permite {1 if emoji_ok else 0}")
    achou = [c for c in UNICODE_IA if c in t]
    if achou:
        motivos.append("travessão, seta ou aspas curvas (" + " ".join(achou) + "): use vírgula, "
                       "ponto, parêntese e aspas retas")
    m = _RE_PLACEHOLDER.search(t)
    if m:
        motivos.append(f"placeholder não resolvido: '{m.group(0)}'")
    simples = sem_acento(low)
    for n in nomes:
        alvo = sem_acento(n).lower().strip()
        if alvo and re.search(r"\b" + re.escape(alvo) + r"\b", simples):
            motivos.append(f"cita '{n}': o comentário não nomeia a empresa da conta nem clientes dela")
            break
    for nome, lista in (("pitch/pedido (comentário não vende nem pede conversa)", PITCH),
                        ("elogio vazio (vá direto ao que você traz)", ELOGIO_VAZIO),
                        ("antítese de efeito (afirme o que a coisa é)", ANTITESE),
                        ("tell de IA", TELLS)):
        for pat in lista:
            mm = re.search(pat, low)
            if mm:
                motivos.append(f"{nome}: '{mm.group(0)}'")
                break
    hits = [mm.group(0) for pat in LEXICO_IA for mm in re.finditer(r"\b" + pat + r"\b", low)]
    if len(hits) > 1:
        motivos.append(f"léxico de IA acumulado ({', '.join(sorted(set(hits)))})")
    for w, teto in TIQUES.items():
        n = len(re.findall(r"\b" + w + r"\b", low))
        if n > teto:
            motivos.append(f"tique '{w}' {n}x (máx. {teto})")
    tk = set(tokens(t))
    ruins = [p for p in proibidas if sem_acento(p).lower() in tk]
    if ruins:
        motivos.append("palavra que a revisão proibiu para esta conta: " + ", ".join(ruins))
    ab = abertura(t)
    if ab and ab in set(aberturas):
        motivos.append(f"mesma abertura de outro comentário recente: '{ab}'")
    ng = _ngrams(t)
    for r in recentes:
        col = ng & _ngrams(r)
        if col:
            motivos.append(f"trecho repetido de comentário recente: \"{max(col, key=len)}\"")
            break
    return motivos
# ============================================================================
# 2. Qual post entra na rodada (e a regra nº 1)
# ============================================================================
JANELA_H = {"linkedin": 14 * 24, "x": 48}
PREFERIDA_H = {"linkedin": 24, "x": 6}     # as primeiras horas valem mais (12/11/2026: era 72 no LinkedIn)
POST_MIN_CHARS = 60
DESCANSO_AUTOR_DIAS = {"linkedin": 7, "x": 3}
FATOR_CANDIDATOS = 1.5
HORAS_SEM_TEXTO = 24
IDIOMAS = ("pt", "en", "es")
RX_NAO_COMENTAR = re.compile(
    r"\bwe'?re hiring\b|\bhiring\b|\bjob opening\b|\bapply (now|here)\b|\bestamos contratando\b|"
    r"\bvagas? (aberta|abertas|de)\b|\bcandidate-se\b|\binscreva-se\b|\blink na bio\b|\bgiveaway\b|"
    r"\bsorteio\b|\bsorteo\b|\bcupom\b|\bdiscount code\b|\bc[oó]digo de desconto\b|\bvacante\b", re.I)

# Palavras funcionais que só existem numa das três línguas (as comuns a PT e ES ficaram de fora).
_FUNC = {
    "pt": {"não", "uma", "com", "os", "é", "mais", "foi", "ao", "seu", "sua", "isso", "muito",
           "também", "já", "pra", "você", "num", "numa", "pelo", "pela", "das", "dos", "nós", "mas",
           "são", "ainda", "quando", "então"},
    "en": {"the", "and", "is", "are", "of", "to", "in", "that", "it", "for", "with", "this", "was",
           "you", "we", "they", "on", "not", "be", "have", "has", "but", "what", "from", "our",
           "their", "how", "when"},
    "es": {"el", "los", "las", "y", "un", "una", "es", "con", "del", "lo", "pero", "más", "este",
           "muy", "también", "ya", "hay", "sus", "nuestro", "nuestra", "cuando", "entonces", "son"},
}

# Situações finais: nada mais muda o post (só a curtida, que é independente).
FINAIS = {"comentado", "incerto", "comentando", "ja_comentado", "descartado", "vencido"}
# Situações em que o autor está "ocupado": um post dele já espera texto, revisão ou postagem.
OCUPAM_AUTOR = {"selecionado", "rascunho", "aprovado", "comentando"}
COM_TEXTO = ("rascunho", "aprovado", "comentando", "comentado", "incerto")


def idioma(texto):
    """'pt', 'en', 'es' ou '' (indeciso), contando palavras funcionais. Sem biblioteca."""
    tk = re.findall(r"[a-záàâãéêíóôõúçñ]+", (texto or "").lower())
    if len(tk) < 5:
        return ""
    pts = {k: sum(1 for w in tk if w in v) for k, v in _FUNC.items()}
    ordem = sorted(pts.items(), key=lambda kv: kv[1], reverse=True)
    (melhor, n1), (_, n2) = ordem[0], ordem[1]
    if n1 < 2 or n1 < n2 * 1.5:
        return ""
    return melhor


def estados(eventos):
    """{id: situação do post} a partir dos eventos do registro de UMA rede, na ordem em que vieram.

    Curtida é independente do comentário (`curtiu`). Intenção de comentar sem desfecho fica como
    'comentando', que é final: pode ter saído, então nunca se tenta de novo."""
    posts = {}
    for e in eventos:
        pid, ev = e.get("id"), e.get("ev")
        if not pid or not ev:
            continue
        pid = str(pid)
        r = posts.setdefault(pid, {"estado": None, "curtiu": False, "texto": None})
        for k in ("canon", "autor"):
            if e.get(k) and not r.get(k):
                r[k] = str(e[k])
        acao = e.get("acao")
        if acao == "curtir":
            if ev in ("intencao", "confirmado", "incerto"):
                r["curtiu"] = True           # intenção sem desfecho conta: curtir de novo DEScurte
                r["curtida_feita"] = r.get("curtida_feita") or ev != "intencao"
            elif ev == "desistiu" and not r.get("curtida_feita"):
                # Desistiu antes do clique: não curtiu. Tenta de novo uma vez só (não reabre o post a
                # cada rodada); se a curtida já estava lá, conta como curtido.
                r["desistencias"] = r.get("desistencias", 0) + 1
                r["curtiu"] = r["desistencias"] >= 2 or bool(re.search(r"j[aá]'? curtido", e.get("motivo") or ""))
            continue
        if acao == "comentar":
            if ev == "intencao":
                r["estado"], r["comentou_em"] = "comentando", e.get("quando")
                r["texto"] = e.get("texto") or r["texto"]
            elif ev == "confirmado":
                r["estado"], r["link"] = "comentado", e.get("link")
            elif ev == "incerto":
                r["estado"] = "incerto"
            elif ev == "desistiu" and r["estado"] == "comentando":
                r["estado"] = "aprovado"
                r.pop("comentou_em", None)
            continue
        if ev == "selecionado":
            for k in ("nome", "url", "data", "trecho", "fonte", "n_comentarios"):
                if e.get(k) is not None:
                    r[k] = e[k]
            r.setdefault("selecionado_em", e.get("quando"))
            if r["estado"] is None:
                r["estado"] = "selecionado"
            continue
        if r["estado"] in FINAIS:
            continue
        if ev == "rascunho":
            r["estado"], r["texto"], r["voz"] = "rascunho", e.get("texto"), e.get("voz")
        elif ev == "aprovado":
            r["estado"] = "aprovado"
        elif ev == "editado":
            r["estado"], r["texto"], r["forcado"] = "aprovado", e.get("depois"), bool(e.get("forcado"))
        elif ev in ("descartado", "pulado", "vencido", "ja_comentado"):
            r["estado"] = ev
            if ev == "ja_comentado" and e.get("comentou_em"):
                # A conta já falou com esse autor por fora do Replai, e a hora é conhecida (no X, a
                # data da resposta dela): o descanso por autor conta dali.
                r.setdefault("comentou_em", e["comentou_em"])
    return posts


def tocados(reg):
    """Ids que nunca voltam: o id e o canônico de TODO post com qualquer situação no registro."""
    out = set()
    for pid, r in reg.items():
        out.add(pid)
        if r.get("canon"):
            out.add(str(r["canon"]))
    return out


def autores_em_descanso(reg, rede, agora):
    lim = agora - timedelta(days=DESCANSO_AUTOR_DIAS[rede])
    out = set()
    for r in reg.values():
        if not r.get("autor"):
            continue
        q = data_de(r.get("comentou_em"))
        if r["estado"] in OCUPAM_AUTOR or (q and q >= lim and r["estado"] in ("comentado", "incerto", "ja_comentado")):
            out.add(r["autor"])
    return out


def idade_h(post, agora):
    d = data_de(post.get("data"))
    return None if d is None else (agora - d).total_seconds() / 3600


def fora_da_janela(data, rede, agora):
    h = idade_h({"data": data}, agora)
    return h is not None and h > JANELA_H[rede]


def motivo_fora(p, rede, agora, ja, descanso):
    """Por que o post NÃO entra na rodada (str), ou None."""
    if str(p["id"]) in ja or str(p.get("canon") or "") in ja:
        return "já tocado pela conta"
    if p.get("repost_puro"):
        return "repost sem texto"
    if p.get("resposta"):
        return "resposta a outro post"
    if len((p.get("texto") or "").strip()) < POST_MIN_CHARS:
        return "texto curto"
    if fora_da_janela(p.get("data"), rede, agora):
        return "fora da janela"
    if (p.get("idioma") or "") not in IDIOMAS + ("",):
        return "idioma"
    if RX_NAO_COMENTAR.search(p.get("texto") or ""):
        return "vaga, venda ou sorteio"
    if p.get("autor") in descanso:
        return "autor em descanso"
    return None


def pontuar(p, rede, agora):
    """Quanto maior, antes. Prioridade da lista, idade (preferida > janela), poucos comentários
    ainda (aparecer entre os primeiros) e engajamento por hora."""
    s = 30.0 if p.get("prioridade") == "alta" else 0.0
    h = idade_h(p, agora)
    pref, jan = PREFERIDA_H[rede], JANELA_H[rede]
    if h is not None:
        # contínua (sem salto na idade preferida): 40 ao nascer, 10 no fim da preferida, 0 no fim da janela
        s += 10 + 30 * max(0.0, 1 - h / pref) if h <= pref else 10 * max(0.0, 1 - (h - pref) / max(1, jan - pref))
    nc = p.get("n_comentarios")
    if nc is not None:
        s += 15 if nc <= 20 else (5 if nc <= 60 else 0)
    nl = p.get("n_curtidas")
    if nl is not None and h is not None:
        s += min(15.0, nl / (h + 2))
    return s


def selecionar(posts, rede, agora, reg, cota):
    """(escolhidos, fora). Escolhidos: no máximo ceil(1.5 × cota), um por autor, do mais bem
    pontuado para baixo. Fora: [(post, motivo)]. Post já no registro, pelo id ou pelo canônico,
    nunca volta: é a regra nº 1."""
    if cota <= 0:
        return [], [(p, "cota do dia") for p in posts]
    ja, descanso = tocados(reg), autores_em_descanso(reg, rede, agora)
    vistos, bons, fora = set(), [], []
    for p in posts:
        chaves = {str(p["id"]), str(p.get("canon") or p["id"])}
        if chaves & vistos:
            fora.append((p, "repetido na coleta"))
            continue
        vistos |= chaves
        m = motivo_fora(p, rede, agora, ja, descanso)
        if m:
            fora.append((p, m))
        else:
            bons.append(p)
    bons.sort(key=lambda p: pontuar(p, rede, agora), reverse=True)
    n = math.ceil(cota * FATOR_CANDIDATOS)
    escolhidos, autores = [], set()
    for p in bons:
        if p.get("autor") in autores:
            fora.append((p, "outro post do mesmo autor na rodada"))
        elif len(escolhidos) >= n:
            fora.append((p, "abaixo do corte"))
        else:
            escolhidos.append(p)
            autores.add(p.get("autor"))
    return escolhidos, fora


def corpus_recente(reg, agora, dias=30, excluir=None):
    """Textos da conta (publicados ou a caminho) dos últimos `dias`: a régua anti-repetição."""
    lim = agora - timedelta(days=dias)
    out = []
    for pid, r in reg.items():
        if pid == excluir or r["estado"] not in COM_TEXTO or not r.get("texto"):
            continue
        q = data_de(r.get("comentou_em") or r.get("selecionado_em"))
        if q is None or q >= lim:
            out.append(r["texto"])
    return out


def aberturas_recentes(reg, n=10, excluir=None):
    com = [(r.get("comentou_em") or r.get("selecionado_em") or "", r["texto"]) for pid, r in reg.items()
           if pid != excluir and r["estado"] in COM_TEXTO and r.get("texto")]
    com.sort(reverse=True)
    return [abertura(t) for _q, t in com[:n]]


def fila_de_postagem(reg, so=None):
    """O que o `postar` faz: aprovado = curtir e comentar; pulado ainda não curtido = só curtir.
    Rascunho espera a revisão. Ordem: a da seleção."""
    fila = []
    for pid, r in reg.items():
        if so is not None and pid != str(so):
            continue
        if r["estado"] == "aprovado":
            comentar = True
        elif r["estado"] == "pulado" and not r["curtiu"] and r.get("url"):
            comentar = False
        else:
            continue
        fila.append(dict(r, id=pid, comentar=comentar))
    fila.sort(key=lambda x: x.get("selecionado_em") or "")
    return fila


def a_vencer(reg, rede, agora):
    """Ids que viram 'vencido': selecionado há mais de 24h sem texto (a rodada se perdeu) e
    rascunho/aprovado de post que saiu da janela (comentar post velho não serve)."""
    out = []
    for pid, r in reg.items():
        if r["estado"] == "selecionado":
            q = data_de(r.get("selecionado_em"))
            if q and agora - q > timedelta(hours=HORAS_SEM_TEXTO):
                out.append(pid)
        elif r["estado"] in ("rascunho", "aprovado") and fora_da_janela(r.get("data"), rede, agora):
            out.append(pid)
    return out
# ============================================================================
# 3. Quanto ainda cabe e em que ritmo
# ============================================================================
# (padrão, máximo) por DIA e por conta. Não existe flag que passe do máximo, de propósito.
TETO = {"linkedin": {"comentarios": (20, 40), "curtidas": (40, 80)},
        "x": {"comentarios": (15, 30), "curtidas": (30, 60)}}
# Por rodada e por hora valem o mesmo número: com 6 por hora (o rascunho da spec) a rodada de 10
# nunca fechava. O limite por hora segura duas rodadas manuais seguidas.
POR_RODADA = {"linkedin": 10, "x": 8}
POR_HORA = POR_RODADA
AQUECIMENTO = ((7, 0.4), (14, 0.7))          # (dias desde a primeira ação, fração do teto)
HORARIO = {"linkedin": (8, 22), "x": (8, 23)}
PAUSA_COMENTADO = {"linkedin": (60, 180), "x": (90, 240)}
PAUSA_CURTIDO = {"linkedin": (20, 45), "x": (30, 60)}
# Leituras: no LinkedIn, requests à Voyager; no X, páginas abertas (o vigia abre 1 por execução
# quando não há nada novo, e o perfil da conta só quando há candidato).
LEITURA = {"linkedin": {"rodada": 60, "dia": 200, "pausa": (3, 8), "reserva": 15},
           "x": {"rodada": 8, "dia": 200, "pausa": (4, 9), "reserva": 1}}
MAX_RODADA_MIN = 45


def no_horario(rede, agora):
    ini, fim = HORARIO[rede]
    return ini <= agora.hour < fim


def pausa(rede, comentou, rng=random):
    return rng.uniform(*(PAUSA_COMENTADO if comentou else PAUSA_CURTIDO)[rede])


def contagens(eventos, agora):
    """Ações e leituras de HOJE (no fuso do `agora`) e da última hora. Intenção conta como feita (pode ter
    saído); 'desistiu' devolve (falhou antes do clique, nada saiu)."""
    hoje = agora.date()
    c = {"comentarios_dia": 0, "curtidas_dia": 0, "comentarios_hora": 0, "curtidas_hora": 0,
         "leituras_dia": 0}
    for e in eventos:
        q = data_de(e.get("quando"))
        if q is None or q.astimezone(agora.tzinfo).date() != hoje:
            continue
        ev = e.get("ev")
        if ev == "leitura":
            c["leituras_dia"] += 1
            continue
        if ev not in ("intencao", "desistiu") or e.get("acao") not in ("comentar", "curtir"):
            continue
        k = "comentarios" if e["acao"] == "comentar" else "curtidas"
        d = 1 if ev == "intencao" else -1
        c[k + "_dia"] += d
        if agora - q <= timedelta(hours=1):
            c[k + "_hora"] += d
    return c


def primeira_acao(eventos):
    """Quando a conta agiu de verdade pela primeira vez nesta rede (começo do aquecimento)."""
    for e in eventos:
        if e.get("ev") == "confirmado":
            return data_de(e.get("quando"))
    return None


def situacao_paradas(eventos, agora):
    """(pausada, corte). Parada hoje = rede pausada até amanhã. Duas paradas a até 7 dias uma da
    outra = teto pela metade até 7 dias depois da segunda."""
    ps = sorted(d for d in (data_de(e.get("quando")) for e in eventos if e.get("ev") == "parada") if d)
    if not ps:
        return False, False
    # quem opera pode soltar a parada do dia (`liberar`); ela continua contando para o corte de 7 dias
    lib = max((d for d in (data_de(e.get("quando")) for e in eventos if e.get("ev") == "liberada") if d), default=None)
    pausada = ps[-1].astimezone(agora.tzinfo).date() == agora.date() and not (lib and lib >= ps[-1])
    corte = any(b - a <= timedelta(days=7) and agora - b <= timedelta(days=7) for a, b in zip(ps, ps[1:]))
    return pausada, corte


def teto_do_dia(rede, agora, primeira, corte=False, pedido=None):
    """Teto do dia depois do pedido de quem opera (nunca acima do máximo), aquecimento, fim de semana e
    corte por paradas."""
    dias = (agora - primeira).days if primeira else 0
    frac = 1.0
    for limite, f in AQUECIMENTO:
        if dias < limite:
            frac = f
            break
    if agora.weekday() >= 5:
        frac *= 0.5
    if corte:
        frac *= 0.5
    out = {}
    for k, (padrao, maximo) in TETO[rede].items():
        base = padrao if (pedido or {}).get(k) is None else max(0, min(int(pedido[k]), maximo))
        out[k] = max(1, math.floor(base * frac)) if base > 0 else 0
    return out


def sessao_caida(eventos):
    """True se a última notícia da sessão foi a queda: a rede deslogou e nenhum login deu certo depois.
    Enquanto isso o robô não abre a rede (abrir, ver o login e fechar a cada execução do vigia é abrir
    e fechar abas sem parar, e bater na rede deslogado)."""
    for e in reversed(eventos):
        if e.get("ev") in ("sessao_caiu", "sessao_ok"):
            return e["ev"] == "sessao_caiu"
    return False


# Recusa (403) em sequência com a sessão VIVA não é bloqueio da conta: é a rede segurando leituras por um
# tempo. Pausa curta e segue sozinho (12/11/2026: antes parava a rede até o dia seguinte).
PAUSA_LEITURA_MIN = 60


def pausa_de_leitura(eventos, agora):
    """Até quando vale a pausa curta de leitura (datetime), ou None."""
    ate = None
    for e in eventos:
        if e.get("ev") == "pausa_leitura":
            ate = data_de(e.get("ate"))
    return ate if ate and ate > agora else None


def cotas(rede, agora, eventos, pedido=None):
    """O que ESTA rodada ainda pode fazer: {"comentarios", "curtidas", "motivo"} (motivo só
    quando não cabe comentário)."""
    pausada, corte = situacao_paradas(eventos, agora)
    zero = {"comentarios": 0, "curtidas": 0}
    if sessao_caida(eventos):
        return dict(zero, motivo="a sessão caiu: rode o login (até lá o Replai não abre esta rede)")
    ate = pausa_de_leitura(eventos, agora)
    if ate:
        return dict(zero, motivo=f"leitura em pausa até {ate.astimezone(agora.tzinfo):%H:%M} "
                                 "(a rede recusou leituras seguidas; volta sozinha)")
    if pausada:
        return dict(zero, motivo="rede pausada até amanhã (a rede deu sinal hoje)")
    if not no_horario(rede, agora):
        ini, fim = HORARIO[rede]
        return dict(zero, motivo=f"fora do horário ({ini}h às {fim}h)")
    c = contagens(eventos, agora)
    teto = teto_do_dia(rede, agora, primeira_acao(eventos), corte, pedido)
    com = max(0, min(teto["comentarios"] - c["comentarios_dia"], POR_RODADA[rede],
                     POR_HORA[rede] - c["comentarios_hora"]))
    cur = max(0, min(teto["curtidas"] - c["curtidas_dia"], 2 * POR_RODADA[rede],
                     2 * POR_HORA[rede] - c["curtidas_hora"]))
    motivo = None
    if com == 0:
        motivo = ("teto de comentários do dia" if teto["comentarios"] <= c["comentarios_dia"]
                  else "limite por hora (espere um pouco)")
    return {"comentarios": com, "curtidas": cur, "motivo": motivo}


# ============================================================================
# 4. O que a revisão ensinou
# ============================================================================
_PARADAS = set(tokens("de da do das dos que para com uma um por pra mais mas como isso esse essa "
                      "the and that this with from have for your you are was were what when "
                      "el los las una con para pero esto esta"))
SIMILARIDADE_MIN = 0.4   # abaixo disso a revisão reescreveu: não é "cortar palavra"


def palavras_cortadas(antes, depois):
    """Palavras (4+ letras, fora as funcionais) que estavam no rascunho e a revisão tirou."""
    a, d = tokens(antes), tokens(depois)
    if difflib.SequenceMatcher(None, a, d).ratio() < SIMILARIDADE_MIN:
        return set()
    return {w for w in a if len(w) >= 4 and w not in _PARADAS} - set(d)


def proibidas_aprendidas(pares, ignorar=()):
    """Palavras cortadas em 2+ correções diferentes (menos as liberadas na conta)."""
    cont = {}
    for antes, depois in pares:
        for w in palavras_cortadas(antes, depois):
            cont[w] = cont.get(w, 0) + 1
    ign = {sem_acento(x).lower() for x in ignorar}
    return sorted(w for w, n in cont.items() if n >= 2 and w not in ign)


def rodada_limpa(n, editados, descartados):
    return n > 0 and (editados + descartados) <= 0.1 * n


REVISOES_PARA_SOZINHO = 3


def propor_sozinho(eventos):
    """True se as 3 últimas revisões, depois da última troca de modo, foram limpas. É também a trava:
    o modo sozinho não liga antes disso (replai.py conta)."""
    revs = []
    for e in eventos:
        if e.get("ev") == "modo":
            revs = []
        elif e.get("ev") == "revisao":
            revs.append(rodada_limpa(e.get("n", 0), e.get("editados", 0), e.get("descartados", 0)))
    return len(revs) >= REVISOES_PARA_SOZINHO and all(revs[-REVISOES_PARA_SOZINHO:])


# ============================================================================
# 5. Modo vigia: comentar minutos depois do post, não horas
# ============================================================================
# O vigia roda a cada `intervalo_min` (tarefa do Windows), só olha posts com até `idade_max_h` e espera
# um atraso sorteado por post antes de agir: ser sempre o primeiro em 1 minuto é cara de robô.
# No LinkedIn o vigia lê as notificações do sininho (ligado em cada perfil da lista): o post chega com
# atraso de minutos e vive mais que no X, por isso a idade máxima é maior.
VIGIA = {"x": {"intervalo_min": 10, "idade_max_h": 2, "atraso_min": (5, 25), "espera_inicial_s": (0, 90)},
         "linkedin": {"intervalo_min": 15, "idade_max_h": 24, "atraso_min": (5, 25), "espera_inicial_s": (0, 90),
                      "sininhos_por_dia": 40, "pausa_sininho_s": (20, 45),
                      "sininhos_por_execucao": 2}}
VIGIA_TICK_MIN = 5       # a tarefa do Windows roda a cada 5 min; cada rede age no intervalo dela
VIGIA_FOLGA_MIN = 3      # folga para a espera sorteada do começo de cada execução


def atraso_do_post(pid, rede):
    """Minutos de espera depois do post, sorteados UMA vez por post: o mesmo em toda execução."""
    lo, hi = VIGIA[rede]["atraso_min"]
    return lo + int(hashlib.sha1(str(pid).encode()).hexdigest(), 16) % (hi - lo + 1)


def situacao_no_vigia(p, rede, agora):
    """'pronto' (já pode agir), 'cedo' (ainda no atraso) ou 'velho' (passou da idade do vigia)."""
    h = idade_h(p, agora)
    if h is None or h > VIGIA[rede]["idade_max_h"]:
        return "velho"
    if h * 60 < atraso_do_post(p["id"], rede):
        return "cedo"
    return "pronto"
