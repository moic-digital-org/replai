#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · testes PUROS de regra.py (sem rede, sem navegador, sem arquivo).
"""Rodar:  python regra_test.py"""
import sys
from datetime import datetime, timedelta, timezone

import regra as R

BRT = timezone(timedelta(hours=-3))      # os testes fixam o fuso; as regras usam o do `agora`

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_ok = _fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  [OK ] {label}")
    else:
        _fail += 1
        print(f"  [FAIL] {label}")


def reprova(texto, trecho, **kw):
    """True se validar() reprova e algum motivo contém `trecho`."""
    return any(trecho in m for m in R.validar(texto, **kw))


print("\n== 1. validar: comentário bom passa ==")
BOM_PT = ("Off-ramp em real ainda depende de dois ou três parceiros bancários, quem resolver a "
          "conciliação leva o mercado.")
BOM_EN = "Curious how you handle settlement windows when the issuer and the bank sit in different time zones?"
BOM_ES = ("En Argentina el problema es la conversión a pesos, la emisión ya está resuelta por dos o "
          "tres actores.")
check(R.validar(BOM_PT) == [], "PT bom passa")
check(R.validar(BOM_EN) == [], "EN bom passa")
check(R.validar(BOM_ES) == [], "ES bom passa")

print("\n== 2. validar: forma ==")
check(reprova("", "vazio"), "vazio")
check(reprova("Linha um sobre off-ramp em real.\nLinha dois sobre bancos.", "quebra de linha"), "quebra de linha")
check(reprova("Concordo demais.", "curto"), "curto demais")
check(reprova("conciliação bancária " * 15, "caracteres"), "longo demais")
check(reprova(BOM_PT + " #stablecoins", "hashtag"), "hashtag")
check(reprova("Concordo com o @fulano sobre off-ramp em real ainda depender de bancos.", "@"), "@")
check(reprova(BOM_PT + " veja exemplo.com/a", "link"), "link")
check(reprova("Vocês usam parceiro local? E como fica a conciliação no fim do mês?", "perguntas"), "duas perguntas")
EMO = "Off-ramp em real ainda depende de parceiros bancários \U0001F600"
check(reprova(EMO, "emoji"), "emoji sem a voz permitir")
check(R.validar(EMO, emoji_ok=True) == [], "um emoji quando a voz permite")
check(reprova("O ponto central \u2014 a conciliação \u2014 ainda é manual em muitos bancos.", "travessão"), "travessão")
check(reprova("Isso vale para o {company} inteiro, não só para o time de produto.", "placeholder"), "placeholder")

print("\n== 3. validar: conteúdo ==")
MOIC = "Na MOIC a gente vê isso toda semana com bancos médios."
check(reprova(MOIC, "não nomeia", nomes=["MOIC", "Initech"]), "cita um nome que a conta nunca cita")
check(R.validar(MOIC) == [], "sem lista de nomes, nada é barrado por nome")
check(reprova("Happy to chat about how settlement works in practice for banks.", "pitch"), "pitch EN")
check(reprova("Great post! Off-ramp em real ainda depende de parceiros bancários.", "elogio vazio"), "elogio vazio")
check(reprova("Isso não é sobre tecnologia, é sobre distribuição de verdade no mercado.", "antítese"), "antítese PT")
check(reprova("It's not a tech problem, it's a distribution problem for most teams.", "antítese"), "antítese EN")
check(reprova("No es un problema técnico, es de distribución en casi todos los mercados.", "antítese"), "antítese ES")
check(reprova("Here's the thing: settlement is still manual for most mid-size banks.", "tell de IA"), "tell EN")
check(reprova("Vale notar que a conciliação ainda é manual na maioria dos bancos médios.", "tell de IA"), "tell PT")
check(reprova("We delve into a robust setup to navigate settlement risk in banks.", "léxico"), "léxico acumulado")
check(reprova("Actually the bank side actually decides the speed of off-ramp here.", "tique"), "tique")

print("\n== 4. validar: contra a conta ==")
check(reprova(BOM_PT, "proibiu", proibidas=["conciliação"]), "palavra proibida (com ou sem acento)")
check(reprova(BOM_PT, "abertura", aberturas=[R.abertura(BOM_PT)]), "mesma abertura de comentário recente")
check(reprova(BOM_PT, "repetido", recentes=["Hoje ainda depende de dois ou três parceiros bancários para tudo."]),
      "trecho de 5 palavras repetido do corpus")
check(R.validar(BOM_PT, recentes=["Assunto totalmente diferente sobre custódia e emissão."]) == [],
      "corpus sem colisão passa")
check(R.abertura("Off-ramp em real, ainda...") == "off ramp em", "abertura normalizada")
check(R.data_de("2026-09-20T10:00:00.000Z").utcoffset() == timedelta(0), "data com Z")
check(R.data_de("2026-09-20T10:00:00").tzinfo == R.FUSO, "data sem fuso vale o fuso do PC")
check(R.data_de("lixo") is None, "data ilegível")

print("\n== 5. idioma ==")
check(R.idioma("Ainda não sei se isso é o melhor caminho, mas a equipe já decidiu com os dados que tinha.") == "pt", "pt")
check(R.idioma("The issue is that most teams have not solved settlement and it shows in the data.") == "en", "en")
check(R.idioma("El problema es que los bancos todavía no tienen una solución y eso se nota mucho.") == "es", "es")
check(R.idioma("ok bom") == "", "curto demais: indeciso")

print("\n== 6. registro -> estados ==")
T = datetime(2026, 11, 4, 14, 0, tzinfo=BRT)            # quarta-feira, 14h
Q = T.isoformat()
evs = [
    {"quando": Q, "ev": "selecionado", "id": "1", "canon": "1", "autor": "ana", "url": "u1", "data": Q},
    {"quando": Q, "ev": "rascunho", "id": "1", "texto": "t1", "voz": 2},
    {"quando": Q, "ev": "aprovado", "id": "1"},
    {"quando": Q, "ev": "intencao", "id": "1", "acao": "curtir"},
    {"quando": Q, "ev": "confirmado", "id": "1", "acao": "curtir"},
    {"quando": Q, "ev": "intencao", "id": "1", "acao": "comentar", "texto": "t1"},
    {"quando": Q, "ev": "confirmado", "id": "1", "acao": "comentar", "link": "L1"},
    {"quando": Q, "ev": "rascunho", "id": "1", "texto": "outro"},            # depois de final: ignora
    {"quando": Q, "ev": "selecionado", "id": "2", "canon": "9", "autor": "bia"},
    {"quando": Q, "ev": "rascunho", "id": "2", "texto": "t2"},
    {"quando": Q, "ev": "editado", "id": "2", "antes": "t2", "depois": "t2b", "forcado": True},
    {"quando": Q, "ev": "intencao", "id": "2", "acao": "comentar", "texto": "t2b"},
    {"quando": Q, "ev": "desistiu", "id": "2", "acao": "comentar"},
    {"quando": Q, "ev": "selecionado", "id": "3", "autor": "caio"},
    {"quando": Q, "ev": "intencao", "id": "3", "acao": "comentar", "texto": "t3"},
]
reg = R.estados(evs)
check(reg["1"]["estado"] == "comentado" and reg["1"]["curtiu"] and reg["1"]["link"] == "L1", "comentado e curtido")
check(reg["1"]["texto"] == "t1", "evento depois do final não muda nada")
check(reg["2"]["estado"] == "aprovado" and reg["2"]["texto"] == "t2b" and reg["2"]["forcado"],
      "desistiu (antes do clique) volta para aprovado, com o texto editado e a marca de forçado")
check("comentou_em" not in reg["2"], "desistiu apaga o comentou_em")
check(reg["3"]["estado"] == "comentando", "intenção sem desfecho = comentando (conta como feito)")
check(R.tocados(reg) == {"1", "2", "9", "3"}, "tocados inclui o id canônico")

print("\n== 7. seleção ==")


def post(i, horas=2, autor=None, canon=None, **kw):
    d = {"id": str(1000 + i), "canon": canon or str(1000 + i), "rede": "linkedin",
         "autor": autor or f"autor{i}", "nome": f"Autor {i}", "headline": "",
         "texto": "Como vocês estão lidando com a conciliação de stablecoins no fechamento do mês?",
         "data": (T - timedelta(hours=horas)).isoformat(), "n_curtidas": 10, "n_comentarios": 3,
         "repost_puro": False, "url": f"https://www.linkedin.com/feed/update/urn:li:activity:{1000 + i}/",
         "fonte": "lista:Principal", "prioridade": "normal", "idioma": "pt"}
    d.update(kw)
    return d


esc, fora = R.selecionar([post(1), post(2, repost_puro=True), post(3, texto="curto"),
                          post(4, horas=15 * 24), post(5, idioma="fr"),
                          post(6, texto="We're hiring! Apply now for our settlement engineer role, remote first."),
                          post(7, autor="ana")], "linkedin", T, reg, 4)
motivos = {p["id"]: m for p, m in fora}
check([p["id"] for p in esc] == ["1001"], "só o post bom entra")
check(motivos["1002"] == "repost sem texto" and motivos["1003"] == "texto curto"
      and motivos["1004"] == "fora da janela" and motivos["1005"] == "idioma"
      and motivos["1006"] == "vaga, venda ou sorteio", "motivos de fora")
check(motivos["1007"] == "autor em descanso", "autor comentado há menos de 7 dias descansa")
esc, fora = R.selecionar([post(10, horas=60), post(11, horas=1), post(12, horas=5, prioridade="alta"),
                          post(13, horas=2, autor="autor11")], "linkedin", T, {}, 4)
check([p["id"] for p in esc] == ["1012", "1011", "1010"], "prioridade alta e post mais novo na frente")
check(dict((p["id"], m) for p, m in fora)["1013"] == "outro post do mesmo autor na rodada", "um post por autor")
esc, fora = R.selecionar([post(20), post(21, canon="1020")], "linkedin", T, {}, 4)
check([p["id"] for p in esc] == ["1020"] and fora[0][1] == "repetido na coleta", "repost do mesmo original na mesma coleta")
esc, _ = R.selecionar([post(30)], "linkedin", T, {}, 0)
check(esc == [], "cota zero não escolhe nada")

print("\n== 8. regra nº 1: rodar 4 vezes no mesmo feed nunca repete ==")
feed = [post(100 + i, horas=1 + i % 40) for i in range(30)]
eventos_ = []
vistos = []
for rodada in range(6):
    esc, _ = R.selecionar(feed, "linkedin", T, R.estados(eventos_), 4)
    vistos.extend(p["id"] for p in esc)
    for p in esc:
        eventos_.append({"quando": Q, "ev": "selecionado", "id": p["id"], "canon": p["canon"],
                         "autor": p["autor"], "url": p["url"], "data": p["data"]})
check(len(vistos) == len(set(vistos)) == 30, "30 posts, 6 rodadas, nenhum repetido")
esc, _ = R.selecionar(feed, "linkedin", T, R.estados(eventos_), 4)
check(esc == [], "feed esgotado: rodada 7 não traz nada")
reg2 = R.estados(eventos_ + [{"quando": Q, "ev": "selecionado", "id": "5000", "canon": "1100"}])
esc, fora = R.selecionar([post(100)], "linkedin", T, reg2, 4)
check(esc == [] and fora[0][1] == "já tocado pela conta", "post já no registro (pelo id ou canônico) nunca volta")

print("\n== 9. corpus, aberturas, fila e vencidos ==")
reg = R.estados(evs)
check(set(R.corpus_recente(reg, T)) == {"t1", "t2b", "t3"}, "corpus: textos com situação de texto")
check(R.corpus_recente(reg, T, excluir="1") == ["t2b", "t3"] or set(R.corpus_recente(reg, T, excluir="1")) == {"t2b", "t3"},
      "corpus sem o próprio post")
check(len(R.aberturas_recentes(reg)) == 3, "aberturas dos textos recentes")
evs_fila = evs + [
    {"quando": Q, "ev": "selecionado", "id": "4", "autor": "d", "url": "u4", "data": Q},
    {"quando": Q, "ev": "pulado", "id": "4", "motivo": "vende curso"},
    {"quando": Q, "ev": "selecionado", "id": "5", "autor": "e", "url": "u5", "data": Q},
    {"quando": Q, "ev": "rascunho", "id": "5", "texto": "t5"},
]
fila = R.fila_de_postagem(R.estados(evs_fila))
check([(i["id"], i["comentar"]) for i in fila] == [("2", True), ("4", False)],
      "fila: aprovado comenta; pulado só curte; rascunho espera revisão")
check([i["id"] for i in R.fila_de_postagem(R.estados(evs_fila), so="4")] == ["4"], "fila de um post só")
velho = (T - timedelta(days=20)).isoformat()
reg3 = R.estados([
    {"quando": (T - timedelta(hours=30)).isoformat(), "ev": "selecionado", "id": "a", "data": Q},
    {"quando": Q, "ev": "selecionado", "id": "b", "data": velho},
    {"quando": Q, "ev": "rascunho", "id": "b", "texto": "x"},
    {"quando": Q, "ev": "selecionado", "id": "c", "data": Q},
])
check(sorted(R.a_vencer(reg3, "linkedin", T)) == ["a", "b"],
      "vence: selecionado há mais de 24h sem texto e rascunho de post fora da janela")

print("\n== 10. horário e pausa ==")
check(R.no_horario("linkedin", T.replace(hour=8)) and not R.no_horario("linkedin", T.replace(hour=22)),
      "LinkedIn das 8h até antes das 22h")
check(R.no_horario("x", T.replace(hour=22, minute=30)), "X até antes das 23h")
import random as _rnd  # noqa: E402
rng = _rnd.Random(1)
check(all(60 <= R.pausa("linkedin", True, rng) <= 180 for _ in range(50)), "pausa depois de comentar: 60 a 180 s")
check(all(20 <= R.pausa("linkedin", False, rng) <= 45 for _ in range(50)), "pausa depois de só curtir: 20 a 45 s")

print("\n== 11. contagens, paradas e tetos ==")
ontem = (T - timedelta(days=1)).isoformat()
ha_2h = (T - timedelta(hours=2)).isoformat()
evc = [
    {"quando": ontem, "ev": "intencao", "acao": "comentar", "id": "z"},
    {"quando": ha_2h, "ev": "intencao", "acao": "comentar", "id": "a"},
    {"quando": Q, "ev": "intencao", "acao": "comentar", "id": "b"},
    {"quando": Q, "ev": "intencao", "acao": "comentar", "id": "c"},
    {"quando": Q, "ev": "desistiu", "acao": "comentar", "id": "c"},
    {"quando": Q, "ev": "intencao", "acao": "curtir", "id": "a"},
    {"quando": Q, "ev": "leitura", "tipo": "posts"},
]
c = R.contagens(evc, T)
check(c["comentarios_dia"] == 2 and c["comentarios_hora"] == 1, "hoje: 2 comentários (desistiu devolve), 1 na última hora")
check(c["curtidas_dia"] == 1 and c["leituras_dia"] == 1, "curtidas e leituras de hoje")
semana3 = T - timedelta(days=21)
check(R.teto_do_dia("linkedin", T, semana3) == {"comentarios": 20, "curtidas": 40}, "a partir da semana 3: padrão")
check(R.teto_do_dia("linkedin", T, None) == {"comentarios": 8, "curtidas": 16}, "antes da primeira ação: 40%")
check(R.teto_do_dia("linkedin", T, T - timedelta(days=8)) == {"comentarios": 14, "curtidas": 28}, "semana 2: 70%")
sab = datetime(2026, 11, 7, 14, 0, tzinfo=BRT)
check(R.teto_do_dia("linkedin", sab, semana3) == {"comentarios": 10, "curtidas": 20}, "fim de semana: metade")
check(R.teto_do_dia("linkedin", T, semana3, corte=True)["comentarios"] == 10, "corte: metade")
check(R.teto_do_dia("linkedin", T, semana3, pedido={"comentarios": 500})["comentarios"] == 40, "pedido acima do máximo vira o máximo")
check(R.teto_do_dia("linkedin", T, semana3, pedido={"comentarios": 5})["comentarios"] == 5, "pedido menor vale")
check(R.situacao_paradas([{"quando": Q, "ev": "parada"}], T) == (True, False), "parada hoje: pausada")
duas = [{"quando": (T - timedelta(days=3)).isoformat(), "ev": "parada"},
        {"quando": (T - timedelta(days=1)).isoformat(), "ev": "parada"}]
check(R.situacao_paradas(duas, T) == (False, True), "duas paradas em 7 dias: corte")
check(R.situacao_paradas(duas, T + timedelta(days=8)) == (False, False), "o corte acaba 7 dias depois")
conf = [{"quando": semana3.isoformat(), "ev": "confirmado", "acao": "comentar", "id": "q"}]
cot = R.cotas("linkedin", T, conf)
check(cot == {"comentarios": 10, "curtidas": 20, "motivo": None}, "por rodada: 10 comentários e 20 curtidas")
check(R.cotas("linkedin", T.replace(hour=23), conf)["motivo"].startswith("fora do horário"), "fora do horário: zero")
check(R.cotas("linkedin", T, conf + [{"quando": Q, "ev": "parada"}])["comentarios"] == 0, "pausada: zero")
cheio = conf + [{"quando": Q, "ev": "intencao", "acao": "comentar", "id": f"k{i}"} for i in range(10)]
check(R.cotas("linkedin", T, cheio)["motivo"] == "limite por hora (espere um pouco)", "10 na última hora: espera")
caiu = conf + [{"quando": Q, "ev": "sessao_caiu"}]
check(R.sessao_caida(caiu) and R.cotas("linkedin", T, caiu)["comentarios"] == 0
      and R.cotas("linkedin", T, caiu)["motivo"].startswith("a sessão caiu"),
      "sessão caída: zero e o motivo manda logar (o vigia não abre a rede de novo a cada execução)")
voltou = caiu + [{"quando": Q, "ev": "sessao_ok"}]
check(not R.sessao_caida(voltou) and R.cotas("linkedin", T, voltou)["comentarios"] == 10
      and not R.sessao_caida(conf), "depois do login que deu certo, volta ao normal")

print("\n== 12. aprendizado ==")
P1 = ("Basicamente o off-ramp em real depende de dois parceiros bancários grandes.",
      "O off-ramp em real depende de dois parceiros bancários grandes.")
P2 = ("Basicamente quem resolve a conciliação no fechamento leva o mercado inteiro.",
      "Quem resolve a conciliação no fechamento leva o mercado inteiro.")
REESCRITA = ("Basicamente tudo depende do banco.", "Concordo com a leitura sobre bancos médios no Brasil hoje.")
check(R.palavras_cortadas(*P1) == {"basicamente"}, "palavra cortada numa correção")
check(R.proibidas_aprendidas([P1]) == [], "um corte só não vira regra")
check(R.proibidas_aprendidas([P1, P2]) == ["basicamente"], "dois cortes viram palavra proibida")
check(R.proibidas_aprendidas([P1, REESCRITA]) == [], "reescrita inteira não conta como corte")
check(R.proibidas_aprendidas([P1, P2], ignorar=["Basicamente"]) == [], "a Bia pode liberar a palavra")
check(R.rodada_limpa(10, 1, 0) and not R.rodada_limpa(10, 1, 1) and not R.rodada_limpa(0, 0, 0), "rodada limpa: até 10% mexido")
rev = lambda n, e: {"quando": Q, "ev": "revisao", "n": n, "editados": e, "descartados": 0}  # noqa: E731
check(R.propor_sozinho([rev(5, 0), rev(5, 0), rev(5, 0)]), "3 limpas seguidas: propõe sozinho")
check(not R.propor_sozinho([rev(5, 0), rev(5, 2), rev(5, 0), rev(5, 0)]), "uma suja no meio: não propõe")
check(not R.propor_sozinho([rev(5, 0), rev(5, 0), {"quando": Q, "ev": "modo", "modo": "revisao"}, rev(5, 0)]),
      "voltar para revisão zera a contagem")

print("\n== 13. X: resposta fica fora; leituras do X ==")
esc, fora = R.selecionar([post(400, rede="x", resposta=True), post(401, rede="x")], "x", T, {}, 4)
check([p["id"] for p in esc] == ["1401"] and dict((p["id"], m) for p, m in fora)["1400"] == "resposta a outro post",
      "resposta a outra pessoa não entra (só post original ou citação)")
check(R.LEITURA["x"]["dia"] >= 6 * 15 * 1, "o teto de leituras do X cabe um vigia a cada 10 min das 8h às 23h")

print("\n== 14. modo vigia ==")
a = R.atraso_do_post("1849000000000000001", "x")
check(5 <= a <= 25 and a == R.atraso_do_post("1849000000000000001", "x"), "atraso sorteado de 5 a 25 min, o mesmo em toda execução")
atrasos = {R.atraso_do_post(str(1849000000000000000 + i), "x") for i in range(200)}
check(len(atrasos) > 10, "o atraso varia de post para post")
p_novo = post(500, horas=0, rede="x")
p_novo["id"] = "1849000000000000001"
p_novo["data"] = (T - timedelta(minutes=a - 1)).isoformat()
check(R.situacao_no_vigia(p_novo, "x", T) == "cedo", "antes do atraso: espera a próxima execução")
p_novo["data"] = (T - timedelta(minutes=a + 1)).isoformat()
check(R.situacao_no_vigia(p_novo, "x", T) == "pronto", "depois do atraso: pronto")
p_novo["data"] = (T - timedelta(hours=3)).isoformat()
check(R.situacao_no_vigia(p_novo, "x", T) == "velho", "mais de 2h: o vigia não pega (a rodada comum ainda pode)")

print("\n== 15. já respondido com hora conhecida dá descanso ao autor ==")
evj = [{"quando": Q, "ev": "ja_comentado", "id": "j1", "autor": "carla", "comentou_em": (T - timedelta(minutes=10)).isoformat()},
       {"quando": Q, "ev": "ja_comentado", "id": "j2", "autor": "davi"}]
desc = R.autores_em_descanso(R.estados(evj), "x", T)
check("carla" in desc and "davi" not in desc, "com a hora da resposta, o autor descansa; sem a hora, não")

print("\n== 16. vícios de IA que passavam (revisão de 05/11) ==")
for t in ("Excelente reflexão, o mercado precisa ouvir isso sobre custódia de ativos.",
          "Concordo plenamente, a regulação vai pesar nas exchanges menores este ano.",
          "Great insights! This really resonates with what we see in custody.",
          "Não é sobre tecnologia. É sobre confiança no emissor do token.",
          "A tokenização é crucial para o mercado de crédito brasileiro avançar.",
          "Não é um problema de produto, mas de distribuição nos bancos médios.",
          "Spot-on analysis of the stablecoin market in Brazil this quarter.",
          "Absolutely agree with the point on settlement times in LatAm.",
          "Such a powerful reminder that distribution beats product in B2B.",
          "Sem dúvida, um tema extremamente relevante para o setor financeiro."):
    check(R.validar(t), f"barra: {t[:48]}")
for t in ("Não é à toa, é o terceiro trimestre seguido de queda no volume das exchanges.",
          "O off-ramp em real ainda depende de dois ou três parceiros bancários grandes.",
          "A análise fundamental do token ignora quem segura a liquidez na ponta.",
          "Isso não é simples, mas o Pix mostrou que dá para padronizar rápido."):
    check(not R.validar(t), f"deixa passar: {t[:48]}")

print("\n== 17. curtida que desistiu antes do clique ==")
evc = [{"quando": Q, "ev": "selecionado", "id": "c1", "url": "u"}, {"quando": Q, "ev": "pulado", "id": "c1"},
       {"quando": Q, "ev": "intencao", "id": "c1", "acao": "curtir"},
       {"quando": Q, "ev": "desistiu", "id": "c1", "acao": "curtir", "motivo": "botão de curtir não achado"}]
check(not R.estados(evc)["c1"]["curtiu"] and R.fila_de_postagem(R.estados(evc)),
      "botão não achado: não curtiu, volta à fila uma vez")
evc2 = evc + evc[2:]
check(R.estados(evc2)["c1"]["curtiu"] and not R.fila_de_postagem(R.estados(evc2)),
      "segunda desistência: não reabre o post a cada rodada")
evc3 = evc[:3] + [dict(evc[3], motivo="ja' curtido (clicar de novo descurtiria)")]
check(R.estados(evc3)["c1"]["curtiu"], "já estava curtido: conta como curtido")
evc4 = evc[:3] + [{"quando": Q, "ev": "incerto", "id": "c1", "acao": "curtir"}, evc[3]]
check(R.estados(evc4)["c1"]["curtiu"], "clique incerto nunca volta (curtir de novo descurte)")

print("\n== liberar a parada do dia ==")
_t = datetime(2026, 11, 4, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
_q = lambda m: (_t - timedelta(minutes=m)).isoformat()  # noqa: E731
_evs = [{"quando": _q(60), "ev": "parada"}]
check(R.situacao_paradas(_evs, _t)[0], "parada hoje: pausada")
_evs.append({"quando": _q(30), "ev": "liberada"})
check(not R.situacao_paradas(_evs, _t)[0], "liberada depois da parada: solta no mesmo dia")
_evs.append({"quando": _q(10), "ev": "parada"})
check(R.situacao_paradas(_evs, _t)[0], "parada nova depois da liberação: volta a valer")
_evs = [{"quando": (_t - timedelta(days=3)).isoformat(), "ev": "parada"}, {"quando": _q(60), "ev": "parada"},
        {"quando": _q(30), "ev": "liberada"}]
check(R.situacao_paradas(_evs, _t) == (False, True), "liberada não apaga a parada: o corte de 7 dias continua")

print("\n== primeiras horas na frente ==")
_agora = datetime(2026, 11, 4, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
_p = lambda h: {"id": str(h), "data": (_agora - timedelta(hours=h)).isoformat()}  # noqa: E731
check(R.pontuar(_p(2), "linkedin", _agora) > R.pontuar(_p(20), "linkedin", _agora) > R.pontuar(_p(30), "linkedin", _agora),
      "LinkedIn: post de 2 h na frente do de 20 h, que vem antes do de 30 h")
check(R.pontuar(_p(30), "linkedin", _agora) <= 10, "LinkedIn: passou de 24 h, vale pouco (só entra se faltar post novo)")

print(f"\nOK: {_ok} | FALHOU: {_fail}")
sys.exit(1 if _fail else 0)
