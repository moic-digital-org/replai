#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Replai · testes da CLI com pasta temporária, Voyager falsa e tela falsa.
# Sem rede e sem navegador. O relógio do replai é fixo numa quarta-feira às 14h.
"""Rodar:  python replai_test.py"""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="replai-test-"))
os.environ["REPLAI_DIR"] = str(TMP / "Replai")
os.environ["CAMPANHA_DIR"] = str(TMP / "Campanha LinkedIn")
os.environ["REPLAI_ESCONDIDO"] = "1"          # os testes rodam no próprio processo (sem área escondida)

import regra as R  # noqa: E402
import replai  # noqa: E402
from openpyxl import Workbook, load_workbook  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

T = datetime(2026, 11, 4, 14, 0, tzinfo=timezone(timedelta(hours=-3)))     # quarta-feira, 14h
replai.agora = lambda: T
_ok = _fail = 0


def check(cond, label):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f"  [OK ] {label}")
    else:
        _fail += 1
        print(f"  [FAIL] {label}")


def rodar(*argv):
    """(código, saída) de um comando; a saída vem como JSON quando é JSON."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cod = replai.main(list(argv))
    txt = buf.getvalue()
    try:
        return cod, json.loads(txt)
    except ValueError:
        return cod, txt


print("\n== 1. quem opera, conta e lista ==")
cod, r = rodar("checar")
check(any("quem opera" in f for f in r["falta"]), "checar pede quem opera")
cod, r = rodar("operador", "--nome", "Bia", "--idioma", "pt")
check(cod == 0 and r["nome"] == "Bia" and replai.idioma() == "pt", "quem opera: nome e idioma")
(replai.CAMPANHA / "_navegador").mkdir(parents=True)          # a campanha de DM existe neste PC
cod, r = rodar("conta", "--nome", "Lúcia Prado")
check(cod == 0 and r["conta"] == "Lucia", "conta nova vira a pasta Lucia")
check(r["nomes_que_nunca_cita"] == replai.NOMES_PADRAO, "a conta nasce com os nomes do padrão (vazio)")
cod, r = rodar("conta", "--nunca-citar", "Acme", "--pode-citar", "initech")
check("Acme" in r["nomes_que_nunca_cita"] and "Initech" not in r["nomes_que_nunca_cita"],
      "a conta ajusta os nomes que nunca cita")
check(r["redes"]["linkedin"]["ativa"] and not r["redes"]["x"]["ativa"], "LinkedIn ligado, X desligado nesta versão")
check(replai.resolver_conta(None) == "Lucia" and replai.resolver_conta("lúcia prado") == "Lucia",
      "acha a conta sem ser dita e pelo nome com acento")
xl = TMP / "lista.xlsx"
wb = Workbook()
ws = wb.active
ws.append(["Name", "LinkedIn URL", "Priority"])
ws.append(["Ana Lima", "https://www.linkedin.com/in/ana-lima/", "alta"])
ws.append(["Bruno Reis", "linkedin.com/in/bruno-reis", ""])
ws.append(["Ana de novo", "https://www.linkedin.com/in/Ana-Lima", ""])
ws.append(["Sem perfil", "", ""])
ws.append(["Carla Dias", "https://www.linkedin.com/in/carla-dias?trk=x", ""])
wb.save(xl)
cod, r = rodar("lista", "--rede", "linkedin", "--nome", "Principal", "--excel", str(xl))
check(cod == 0 and r["importados"] == 3 and r["perfis_ativos"] == 3,
      "3 perfis entram; duplicado e linha sem perfil ficam fora")
c = replai.ler_conta("Lucia")
perfis = replai.perfis_da_rede("Lucia", c, "linkedin")
check([p["chave"] for p in perfis] == ["ana-lima", "bruno-reis", "carla-dias"], "chaves são as vanities")
check(perfis[0]["prioridade"] == "alta" and perfis[1]["prioridade"] == "normal", "prioridade da linha")
cod, r = rodar("lista", "--rede", "linkedin", "--nome", "Principal", "--excel", str(xl))
check(r["importados"] == 0, "importar de novo não duplica")
check(replai.chave_perfil("x", "https://x.com/Fulano_1") == "fulano_1" and replai.chave_perfil("x", "@Fulano") == "fulano",
      "chave do X (para a fase 2)")

print("\n== 2. status, planilha, registro e trava ==")
cod, r = rodar("status")
check(cod == 0 and "linkedin" in r["redes"] and "x" not in r["redes"], "status só da rede ligada")
check(r["redes"]["linkedin"]["cota_agora"]["comentarios"] == 8, "aquecimento da semana 1: 8 comentários")
check(Path(r["planilha"]).exists(), "planilha criada")
wbp = load_workbook(r["planilha"])
check(wbp.sheetnames[0] == "Resumo" and "LinkedIn - Principal" in wbp.sheetnames and "Ações" in wbp.sheetnames,
      "abas Resumo, lista e Ações")
rodar("operador", "--idioma", "en")
check(replai.sincronizar_planilha("Lucia", replai.ler_conta("Lucia")), "planilha reescrita em inglês")
wbp = load_workbook(r["planilha"])
check(wbp.sheetnames[0] == "Summary" and "Actions" in wbp.sheetnames and "Ações" not in wbp.sheetnames,
      "quem opera em inglês: abas em inglês")
check(len(replai.perfis_da_rede("Lucia", replai.ler_conta("Lucia"), "linkedin")) == 3,
      "a lista com cabeçalho em português continua sendo lida")
rodar("operador", "--idioma", "pt")
replai.sincronizar_planilha("Lucia", replai.ler_conta("Lucia"))
replai.registrar("Lucia", "linkedin", "leitura", tipo="posts")
check(replai.eventos("Lucia", "linkedin")[-1]["ev"] == "leitura", "registro grava e lê")
with replai.Trava(TMP / "t.lock"):
    try:
        with replai.Trava(TMP / "t.lock"):
            check(False, "trava dupla devia falhar")
    except replai.Erro as e:
        check(e.codigo == 3, "segunda trava = ocupado (código 3)")
check(not (TMP / "t.lock").exists(), "a trava some ao sair")
check(replai.trava_de("Lucia", c, "linkedin") == replai.CAMPANHA / ".enviando.lock",
      "LinkedIn usa a trava da campanha")
check(replai.sessao_de("Lucia", c, "linkedin") == replai.CAMPANHA / "_navegador",
      "LinkedIn usa a sessão da campanha")
cod, r = rodar("coletar", "--rede", "x")
check(cod == 2 and "erro" in r, "rede desligada (ou comando que ainda não existe) dá erro de configuração")
cod, r = rodar("checar")
check(cod == 0 and not r["pronto"] and any("login no linkedin" in f for f in r["falta"]),
      "checar aponta o que falta (login)")

print("\n== 3. coletar (Voyager falsa) ==")
import linkedin as L  # noqa: E402

T_MS = int(T.timestamp() * 1000) + 1000


def act(horas):
    """Um id de activity cuja data é T menos `horas` (o inverso de L.data_da_activity)."""
    return str(int((T - timedelta(hours=horas)).timestamp() * 1000) << 22)


def lp(vanity, nome, horas, n_com=3):
    aid = act(horas)
    return {"activity_id": aid, "data": L.data_da_activity(aid, T_MS),
            "texto": f"{nome} pergunta: como vocês estão lidando com a conciliação de stablecoins no fechamento do mês?",
            "autor": nome, "autor_headline": "Head de Pagamentos", "autor_vanity": vanity,
            "n_curtidas": 10, "n_comentarios": n_com, "repost_puro": False, "original_id": None,
            "url": L.url_do_post(f"urn:li:activity:{aid}")}


class VoyFalsa:
    def __init__(self, por_urn, comentados=()):
        self.por_urn, self.comentados, self.feitas = por_urn, set(comentados), 0

    def me(self):
        return {"urn": "ACoAAme", "vanity": "lucia-prado", "nome": "Lúcia Prado"}

    def urn_do_perfil(self, vanity):
        self.feitas += 1
        return "URN-" + vanity

    def posts(self, urn, count=10):
        self.feitas += 1
        return list(self.por_urn.get(urn, []))

    def comentario_da_conta(self, aid, me):
        self.feitas += 1
        return {"comment_urn": f"urn:li:comment:(activity:{aid},1)"} if aid in self.comentados else None


POSTS = {"URN-ana-lima": [lp("ana-lima", "Ana Lima", 2), lp("ana-lima", "Ana Lima", 30)],
         "URN-bruno-reis": [lp("bruno-reis", "Bruno Reis", 3), lp("bruno-reis", "Bruno Reis", 31)],
         "URN-carla-dias": [lp("carla-dias", "Carla Dias", 4), lp("carla-dias", "Carla Dias", 32)]}
ANA_A, BRUNO_A = POSTS["URN-ana-lima"][0]["activity_id"], POSTS["URN-bruno-reis"][0]["activity_id"]
CARLA_A, CARLA_B = POSTS["URN-carla-dias"][0]["activity_id"], POSTS["URN-carla-dias"][1]["activity_id"]
voy = VoyFalsa(POSTS, comentados={CARLA_A})
c = replai.ler_conta("Lucia")
res0 = replai.coletar_linkedin("Lucia", c, replai.perfis_da_rede("Lucia", c, "linkedin"), 8, voy, simular=True)
check(res0["simulacao"] and res0["candidatos"] == 2, "simulação lê e escolhe")
check(not any(e["ev"] in ("selecionado", "ja_comentado") for e in replai.eventos("Lucia", "linkedin")),
      "simulação não grava seleção")
check(replai.rodada_atual("Lucia", "linkedin")[0] is True, "a rodada atual é a simulação")
res = replai.coletar_linkedin("Lucia", replai.ler_conta("Lucia"),
                              replai.perfis_da_rede("Lucia", c, "linkedin"), 8, voy)
check(res["candidatos"] == 2 and res["perfis_lidos"] == 3, "um post por autor; o da Carla já tinha comentário da conta")
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(reg[ANA_A]["estado"] == "selecionado" and reg[BRUNO_A]["estado"] == "selecionado", "selecionados no registro")
check(reg[CARLA_A]["estado"] == "ja_comentado", "comentário feito fora do Replai vira ja_comentado")
check(replai.ler_conta("Lucia")["redes"]["linkedin"]["perfil"].endswith("/lucia-prado/"),
      "perfil da conta aprendido do /me")
res2 = replai.coletar_linkedin("Lucia", replai.ler_conta("Lucia"),
                               replai.perfis_da_rede("Lucia", c, "linkedin"), 8, voy)
sim, dados = replai.rodada_atual("Lucia", "linkedin")
check(res2["candidatos"] == 1 and res2["perfis_lidos"] == 1, "2ª coleta: Ana e Bruno ocupados, só a Carla é lida")
check(not sim and {p["id"] for p in dados["posts"]} == {ANA_A, BRUNO_A, CARLA_B},
      "o pool acumula: os que esperam texto continuam, o novo entra")
voy_errado = VoyFalsa(POSTS)
voy_errado.me = lambda: {"urn": "x", "vanity": "outra-pessoa"}
try:
    replai.coletar_linkedin("Lucia", replai.ler_conta("Lucia"), [], 8, voy_errado)
    check(False, "conta errada devia parar")
except replai.Erro as e:
    check(e.codigo == 4, "conta errada logada = código 4")

print("\n== 4. lote e escrever ==")
VOZ = ("# Voz · Lúcia Prado · LinkedIn · versão 1 · calibrada em 2026-11-01\n"
       "## Quem fala\nCEO.\n## Assuntos com propriedade\nPagamentos.\n## Evitar\nPolítica.\n"
       "## Tom\n| Emoji | nunca |\n## Forma\nCurto.\n## Usa / Nunca usa\n- Usa: dado\n"
       "## Regras aprendidas\n- nenhuma\n## Exemplos aprovados\n- nenhum\n")
cod, r = rodar("lote", "--rede", "linkedin")
check(cod == 2 and "voz" in r["erro"], "sem voz, o lote não sai")
replai.voz_arq("Lucia", "linkedin").write_text(VOZ, encoding="utf-8")
cod, txt = rodar("lote", "--rede", "linkedin")
check(cod == 0 and "## comum" in txt and "## linkedin" in txt and "## x" not in txt, "lote leva só as seções da rede")
check("versão 1" in txt and ANA_A in txt and BRUNO_A in txt and CARLA_B in txt and "Como entregar" in txt,
      "lote leva a voz, os 3 posts e como entregar")
check("## Nomes que esta conta nunca cita" in txt and "Acme" in txt, "lote leva os nomes que a conta nunca cita")
saida = replai.rodada_dir("Lucia", "linkedin") / "saida.json"
BOM = ("Off-ramp em real ainda depende de dois ou três parceiros bancários, quem resolver a "
       "conciliação leva o mercado.")
saida.write_text(json.dumps({ANA_A: BOM, BRUNO_A: "-vende curso",
                             CARLA_B: "O ponto central \u2014 a conciliação \u2014 ainda é manual em muitos bancos médios."}),
                 encoding="utf-8")
cod, r = rodar("escrever", "--rede", "linkedin", "--arquivo", str(saida))
check(r["aceitos"] == 1 and r["pulados"] == 1 and CARLA_B in r["reprovados"], "1 aceito, 1 pulado, 1 reprovado (travessão)")
check(r["faltam"] == [CARLA_B], "o reprovado continua esperando texto")
cod, txt = rodar("lote", "--rede", "linkedin")
check("Reprovados na tentativa anterior" in txt and CARLA_B in txt and ANA_A not in txt,
      "o lote seguinte traz só o reprovado, com o motivo")
saida.write_text(json.dumps({CARLA_B: "De novo \u2014 com travessão, o que não pode de jeito nenhum aqui."}),
                 encoding="utf-8")
cod, r = rodar("escrever", "--rede", "linkedin", "--arquivo", str(saida))
check(r["pulados"] == 1 and r["faltam"] == [], "segunda reprovação vira pulado (só curtida)")
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(reg[ANA_A]["estado"] == "rascunho" and reg[ANA_A]["voz"] == 1, "rascunho com a versão da voz")
check(reg[BRUNO_A]["estado"] == "pulado" and reg[CARLA_B]["estado"] == "pulado", "pulados")
cod, txt = rodar("lote", "--rede", "linkedin")
check("Nada para escrever" in txt, "lote vazio quando tudo foi respondido")

print("\n== 5. revisão e aprovação ==")
cod, txt = rodar("revisao", "--rede", "linkedin")
check(txt.startswith("1. Ana Lima") and "→ Off-ramp" in txt, "revisão numerada com o comentário")
dec = replai.rodada_dir("Lucia", "linkedin") / "decisoes.json"
dec.write_text(json.dumps({"1": "ok"}), encoding="utf-8")
cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
check(r["aprovados"] == 1 and r["limpa"] is True and r["esperando"] == 0, "ok aprova e a rodada é limpa")


def rascunho(pid, texto, autor):
    replai.registrar("Lucia", "linkedin", "selecionado", id=pid, autor=autor, nome=autor,
                     url=f"https://teste/{pid}", data=T.isoformat(), trecho="post de teste")
    replai.registrar("Lucia", "linkedin", "rascunho", id=pid, texto=texto, voz=1)


rascunho("7001", "Basicamente o off-ramp em real depende de dois parceiros bancários grandes.", "w1")
rascunho("7002", "Basicamente quem resolve a conciliação no fechamento leva o mercado inteiro.", "w2")
rodar("revisao", "--rede", "linkedin")
dec.write_text(json.dumps({"1": "O off-ramp em real depende de dois parceiros bancários grandes.",
                           "2": "Quem resolve a conciliação no fechamento leva o mercado inteiro."}), encoding="utf-8")
cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
check(r["editados"] == 2 and r["limpa"] is False, "duas correções: rodada não é limpa")
check(r["novas_proibidas"] == ["basicamente"], "palavra cortada duas vezes vira proibida")
check(r["aprendizados_desde_a_voz"] >= 2, "conta os aprendizados desde a voz")
rascunho("7003", "Concordo com a leitura sobre liquidação em bancos médios no Brasil.", "w3")
rodar("revisao", "--rede", "linkedin")
dec.write_text(json.dumps({"1": "Ótimo post, concordo com tudo isso aqui de verdade."}), encoding="utf-8")
cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
check("1" in r["avisos"] and r["editados"] == 0, "texto da Bia reprovado no validador vira aviso, não grava")
dec.write_text(json.dumps({"1": "!Ótimo post, concordo com tudo isso aqui de verdade."}), encoding="utf-8")
cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(r["editados"] == 1 and reg["7003"]["forcado"] and reg["7003"]["estado"] == "aprovado",
      "com '!' a Bia confirma e o texto fica marcado como forçado")
TXT = ["Liquidação em D+0 ainda esbarra no horário do banco correspondente.",
       "Quem opera câmbio sabe que o spread some quando o volume aparece.",
       "O gargalo de custódia aparece antes do de emissão em quase todo piloto."]
for i, texto in enumerate(TXT):
    rascunho(str(7100 + i), texto, f"z{i}")
    rodar("revisao", "--rede", "linkedin")
    dec.write_text(json.dumps({"todos": "ok"}), encoding="utf-8")
    cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
check(r["limpa"] and r["propor_sozinho"], "3 revisões limpas seguidas: propõe passar para sozinho")
rascunho("7200", "Prazo de liquidação ainda pesa mais que a tarifa para quem importa insumo.", "z9")
rodar("revisao", "--rede", "linkedin")
dec.write_text(json.dumps({"1": "-"}), encoding="utf-8")
cod, r = rodar("aprovar", "--rede", "linkedin", "--arquivo", str(dec))
check(r["descartados"] == 1 and R.estados(replai.eventos("Lucia", "linkedin"))["7200"]["estado"] == "descartado",
      "'tira' descarta (nem curte)")

print("\n== 6. postar (tela falsa) ==")


class PaginaFalsa:
    def __init__(self):
        self.url = ""

    def goto(self, url, **kw):
        self.url = url

    def wait_for_timeout(self, ms):
        pass


class TelaFalsa:
    """O pedaço do módulo linkedin que o postar usa, sem navegador."""
    VoyagerErro, ERRO_BLOQUEIO, ERRO_SESSAO = L.VoyagerErro, L.ERRO_BLOQUEIO, L.ERRO_SESSAO
    url_do_comentario = staticmethod(L.url_do_comentario)

    def __init__(self, voy, ja_comentados=(), captcha_em=()):
        self.voy, self.ja, self.captcha = voy, set(ja_comentados), set(captcha_em)
        self.comentou, self.curtiu = {}, {}

    def _alvo(self, page, ids):
        return any(page.url.endswith("/" + x) for x in ids)

    def bloqueio(self, page):
        return "CAPTCHA" if self._alvo(page, self.captcha) else None

    def controles(self, page, aid):
        return {"achou_post": True, "like": {"achou": True, "pressionado": "false"}}

    def curtir(self, page, aid):
        self.curtiu[aid] = self.curtiu.get(aid, 0) + 1
        return True, "ok", "pos_clique"

    def comentarios_na_pagina(self, page, vanity, trecho=""):
        return {"da_conta": self._alvo(page, self.ja)}

    def comentar(self, page, aid, texto, vanity, rng=None):
        self.comentou[aid] = self.comentou.get(aid, 0) + 1
        self.voy.comentados.add(aid)
        return True, "ok", "pos_clique"


def aprovado(pid, texto, autor):
    rascunho(pid, texto, autor)
    replai.registrar("Lucia", "linkedin", "aprovado", id=pid)


aprovado("9001", "Liquidação de stablecoin em banco médio ainda passa por conciliação manual.", "w9")
voy = VoyFalsa(POSTS)
tela = TelaFalsa(voy, ja_comentados={"9001"})
c = replai.ler_conta("Lucia")
fila = R.fila_de_postagem(R.estados(replai.eventos("Lucia", "linkedin")))
check(sum(1 for i in fila if i["comentar"]) == 8 and sum(1 for i in fila if not i["comentar"]) == 2,
      "fila: 8 para comentar e 2 só para curtir")
res = replai.postar_linkedin("Lucia", c, fila, PaginaFalsa(), voy, voy.me(), acoes=tela, dormir=lambda s: None)
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(all(n == 1 for n in tela.comentou.values()) and all(n == 1 for n in tela.curtiu.values()),
      "nenhum post recebeu dois comentários nem duas curtidas")
check("9001" not in tela.comentou and reg["9001"]["estado"] == "ja_comentado",
      "página mostrando comentário da conta: não comenta")
check(reg[ANA_A]["estado"] == "comentado" and reg[ANA_A].get("link"), "comentado, com o link do comentário")
check(reg[BRUNO_A]["curtiu"] and BRUNO_A not in tela.comentou, "pulado recebe só curtida")
check(reg["7003"]["estado"] == "comentado", "texto forçado pela Bia sai sem revalidar")
check(len(res["comentados"]) == 7 and res["parou"] is None, "7 comentados, sem parada")
check(R.fila_de_postagem(reg) == [], "depois da rodada a fila fica vazia")
res2 = replai.postar_linkedin("Lucia", c, R.fila_de_postagem(reg), PaginaFalsa(), voy, voy.me(),
                              acoes=tela, dormir=lambda s: None)
check(res2["comentados"] == [] and all(n == 1 for n in tela.comentou.values()), "rodar de novo não comenta nada")


class TelaSemConfirmar(TelaFalsa):
    """O layout muda: o comentário sai, mas a tela não acha o trecho. `sai` diz se ele saiu de verdade."""
    def __init__(self, voy, sai):
        super().__init__(voy)
        self.sai = sai

    def comentar(self, page, aid, texto, vanity, rng=None):
        self.comentou[aid] = self.comentou.get(aid, 0) + 1
        if self.sai:
            self.voy.comentados.add(aid)
        return False, "comentario nao confirmado na pagina", "pos_clique"


aprovado("9003", "Conciliação manual ainda é o custo escondido da liquidação em tempo real.", "w11")
aprovado("9004", "Câmbio de exportador pequeno ainda depende do gerente, não da tela.", "w12")
cotas_de_verdade = R.cotas
R.cotas = lambda *a, **k: {"comentarios": 5, "curtidas": 5, "motivo": None}   # o teto do teste já foi
try:
    for pid, sai in (("9003", True), ("9004", False)):
        fila = [i for i in R.fila_de_postagem(R.estados(replai.eventos("Lucia", "linkedin"))) if i["id"] == pid]
        replai.postar_linkedin("Lucia", c, fila, PaginaFalsa(), voy, voy.me(), acoes=TelaSemConfirmar(voy, sai),
                               dormir=lambda s: None)
finally:
    R.cotas = cotas_de_verdade
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(reg["9003"]["estado"] == "comentado" and reg["9003"].get("link"),
      "tela não confirmou, mas a lista de comentários da rede mostra o da conta: comentado, com link")
check(reg["9004"]["estado"] == "incerto",
      "tela não confirmou e a rede não lista: incerto (nunca volta para a fila)")
aprovado("9002", "Prazo de liquidação no câmbio pesa mais que a tarifa para quem importa.", "w10")
tela.captcha = {"9002"}
res3 = replai.postar_linkedin("Lucia", c, R.fila_de_postagem(R.estados(replai.eventos("Lucia", "linkedin"))),
                              PaginaFalsa(), voy, voy.me(), acoes=tela, dormir=lambda s: None)
evs = replai.eventos("Lucia", "linkedin")
check(res3["parou"] and "CAPTCHA" in res3["parou"] and "9002" not in tela.comentou, "captcha para a rodada antes de agir")
check(R.situacao_paradas(evs, T)[0] and R.cotas("linkedin", T, evs)["comentarios"] == 0, "rede pausada até amanhã")
cod, r = rodar("postar", "--rede", "linkedin")
check(cod == 0 and "pausada" in r["nada_a_fazer"], "postar com a rede pausada não abre o navegador")

print("\n== 7. planilha depois de postar ==")
check(replai.sincronizar_planilha("Lucia", c), "planilha atualizada")
wb = load_workbook(replai.planilha_de("Lucia"))
ws = wb["Ações"]
cab = [x.value for x in ws[1]]
check(ws.max_row - 1 >= 10, "uma linha por post com ação")
i_post, i_nota = cab.index("Post"), cab.index("Nota da revisão")
for row in ws.iter_rows(min_row=2):
    if row[i_post].value == POSTS["URN-ana-lima"][0]["url"]:
        row[i_nota].value = "ruim: genérico demais"
wb.save(replai.planilha_de("Lucia"))
replai.sincronizar_planilha("Lucia", c)
replai.sincronizar_planilha("Lucia", c)
notas = [e for e in replai.eventos("Lucia", "linkedin") if e["ev"] == "nota"]
check(len(notas) == 1 and notas[0]["id"] == ANA_A, "nota da revisão vira aprendizado uma vez só")
wb = load_workbook(replai.planilha_de("Lucia"))
check(any(row[i_nota] == "ruim: genérico demais" for row in wb["Ações"].iter_rows(min_row=2, values_only=True)),
      "a nota continua na planilha reescrita")
lista = [x for x in wb["LinkedIn - Principal"].iter_rows(min_row=2, values_only=True) if x[0] == "Ana Lima"][0]
check(lista[6] == T.date().isoformat(), "Último comentário preenchido na aba da lista")

print("\n== 8. voz ==")
novo = TMP / "voz.md"
novo.write_text(VOZ.replace("versão 1", "versão 9"), encoding="utf-8")
cod, r = rodar("voz", "--rede", "linkedin", "--arquivo", str(novo))
check(cod == 0 and r["versao"] == 2, "voz nova sobe de versão (o cabeçalho é reescrito pelo script)")
check(replai.arq("Lucia", "voz-historico", "voz-linkedin-v1.md").exists(), "versão anterior guardada")
check("versão 2" in replai.voz_atual("Lucia", "linkedin").splitlines()[0], "cabeçalho com a versão nova")
check(replai.data_da_voz("Lucia", "linkedin") == T.isoformat(timespec="seconds"), "evento voz no registro")
ruim = TMP / "voz-ruim.md"
ruim.write_text("# Voz\n## Quem fala\nx\n", encoding="utf-8")
cod, r = rodar("voz", "--rede", "linkedin", "--arquivo", str(ruim))
check(cod == 2 and "seções" in r["erro"], "voz sem as seções é recusada")
cod, r = rodar("voz-pacote", "--rede", "linkedin", "--tipo", "retrato")
check(cod == 2 and "voz-amostra" in r["erro"], "retrato sem amostra pede a leitura antes")
replai.arq("Lucia", "amostra-linkedin.json").write_text(
    json.dumps({"posts": ["Post do Lúcia sobre pagamentos."], "comentarios": []}), encoding="utf-8")
cod, txt = rodar("voz-pacote", "--rede", "linkedin", "--tipo", "retrato")
check("Post do Lúcia sobre pagamentos." in txt and "## Quem fala" in txt and "rascunho-voz-linkedin.md" in txt,
      "pacote do retrato: amostra, molde e onde gravar")
cod, txt = rodar("voz-pacote", "--rede", "linkedin", "--tipo", "aprendizado")
check("Correções na revisão" in txt and "Notas depois de publicado" in txt and "## Voz atual" in txt,
      "pacote de aprendizado: correções, notas e a voz atual")
rodar("operador", "--idioma", "en")
novo.write_text(VOZ.replace("## Quem fala", "## Who speaks").replace("## Tom", "## Tone"), encoding="utf-8")
cod, r = rodar("voz", "--rede", "linkedin", "--arquivo", str(novo))
check(cod == 0 and replai.voz_atual("Lucia", "linkedin").startswith("# Voice · Lúcia Prado · LinkedIn · version 3"),
      "voz com seções em inglês aceita, cabeçalho em inglês")
cod, txt = rodar("voz-pacote", "--rede", "linkedin", "--tipo", "retrato")
check("Idioma de quem opera: en" in txt and "## Who speaks" in txt, "pacote em inglês: molde em inglês")
rodar("operador", "--idioma", "pt")
check(replai.emoji_permitido("| Emoji | esporádico |") and replai.emoji_permitido("| Emoji | occasional |")
      and not replai.emoji_permitido("| Emoji | nunca |")
      and not replai.emoji_permitido("| Emoji | (nunca ou esporádico) |"), "emoji só quando a voz diz que pode")

print("\n== 9. X: lista, coleta e vigia (leitor e tela falsos) ==")
import x as X  # noqa: E402

cod, r = rodar("conta", "--rede", "x", "--ativa", "sim")
check(cod == 0 and r["redes"]["x"]["ativa"] and r["redes"]["x"]["sessao"] == "propria", "X ligado, com sessão própria")
cod, r = rodar("lista", "--rede", "x", "--nome", "Principal", "--x-lista", "https://x.com/i/lists/987?s=20")
check(cod == 0 and r["lista"]["x_lista"] == "https://x.com/i/lists/987", "Lista nativa do X guardada (sem o ?s=)")
cod, r = rodar("lista", "--rede", "linkedin", "--nome", "Principal", "--x-lista", "https://x.com/i/lists/987")
check(cod == 2, "Lista do X só vale para --rede x")
xl2 = TMP / "x.xlsx"
wb = Workbook()
wb.active.append(["Nome", "X"])
wb.active.append(["Carla", "@carla_x"])
wb.save(xl2)
rodar("lista", "--rede", "x", "--nome", "Principal", "--excel", str(xl2))
fontes = replai.fontes_x("Lucia", replai.ler_conta("Lucia"))
check([f["tipo"] for f in fontes] == ["lista", "busca"] and fontes[1]["handles"] == ["carla_x"],
      "fontes: a Lista nativa e uma busca para os @ da aba")


def tw(tid, autor, minutos, texto=None, **kw):
    d = {"id": tid, "texto": texto or f"{autor} says stablecoin settlement still breaks at the bank cut-off every Friday.",
         "data": (T - timedelta(minutes=minutos)).isoformat(), "idioma": "en", "autor": autor, "nome": autor.title(),
         "bio": "Payments", "n_curtidas": 5, "n_comentarios": 1, "curtido": False, "resposta_a": None,
         "retweet_de": None, "citacao_de": None, "url": f"https://x.com/{autor}/status/{tid}"}
    d.update(kw)
    return d


class LeitorFalso:
    def __init__(self, lista, busca=(), respostas=()):
        self._lista, self._busca, self._resp, self.feitas = list(lista), list(busca), list(respostas), 0

    def me(self):
        return "lucia"

    def membros(self, url):
        self.feitas += 1
        return ["ana_x", "bruno_x"]

    def lista(self, url):
        self.feitas += 1
        return list(self._lista)

    def busca(self, handles):
        self.feitas += 1
        return [t for t in self._busca if t["autor"] in handles]

    def respostas_da_conta(self, meu):
        self.feitas += 1
        return list(self._resp)


A_VELHO = tw("9001", "ana_x", 300)                 # 5h: fora do vigia
A_NOVO = tw("9002", "ana_x", 40)                   # 40 min: passou de qualquer atraso
B_CEDO = tw("9003", "bruno_x", 1)                  # 1 min: ainda no atraso
B_RESP = tw("9004", "bruno_x", 30, resposta_a="111")
Z_FORA = tw("9005", "zed", 30)                     # não é da lista
A_RT = tw("9006", "ana_x", 20, texto="RT @zed: algo", retweet_de="9005")
C_BUSCA = tw("9007", "carla_x", 50)
C_JA = tw("9008", "carla_x", 45)
MINHA = tw("9100", "lucia", 10, resposta_a="9008")
leitor = LeitorFalso([A_VELHO, A_NOVO, B_CEDO, B_RESP, Z_FORA, A_RT], busca=[C_BUSCA, C_JA], respostas=[MINHA])
c = replai.ler_conta("Lucia")
res = replai.coletar_x("Lucia", c, 6, leitor, vigia=True)
reg = R.estados(replai.eventos("Lucia", "x"))
sel = {pid for pid, r_ in reg.items() if r_["estado"] == "selecionado"}
check(replai.ler_conta("Lucia")["redes"]["x"]["perfil"] == "https://x.com/lucia", "perfil do X aprendido da conta logada")
check(sel == {"9002"} or sel == {"9002", "9007"},
      "vigia: só post da lista, recente, original e fora do atraso (sem resposta, RT, de fora ou velho)")
check(reg.get("9008", {}).get("estado") == "ja_comentado", "post que a conta já respondeu vira ja_comentado")
check(res["no_atraso"] == 1 and "9003" not in reg, "post no atraso sorteado não é registrado: a próxima execução pega")
check(replai.ler_json(replai.arq("Lucia", "cache-x.json"))["https://x.com/i/lists/987"]["handles"] == ["ana_x", "bruno_x"],
      "membros da Lista guardados por 24h")
res2 = replai.coletar_x("Lucia", replai.ler_conta("Lucia"), 6, leitor, vigia=True)
check(res2["candidatos"] == 0, "rodar o vigia de novo no mesmo feed não traz post repetido")

print("\n== 10. vigia: escreve pelo Claude (falso) e responde ==")
VOZ_X = VOZ.replace("LinkedIn", "X")
replai.voz_arq("Lucia", "x").write_text(VOZ_X, encoding="utf-8")
chamadas = []


def escritor_falso(pacote):
    chamadas.append(pacote)
    ids = [l.split('"')[3] for l in pacote.splitlines() if l.strip().startswith('"id"')]
    if len(chamadas) == 1:                                    # 1ª: um bom e um com travessão
        return {ids[0]: "Bank cut-off on Fridays is where most stablecoin pilots stall in LatAm.",
                **({ids[1]: "Settlement — the real bottleneck."} if len(ids) > 1 else {})}
    outros = ["Weekend settlement is the part nobody budgets for in a pilot.",
              "Cut-off windows matter more than fees once real volume shows up.",
              "Most treasury teams only see the gap after the month-end close."]
    return {i: outros[n] for n, i in enumerate(ids)}


check(replai.extrair_json('```json\n{"1": "ok"}\n```') == {"1": "ok"}, "JSON do escritor com cerca de código")
leitor2 = LeitorFalso([tw("9201", "ana_x", 60), tw("9202", "bruno_x", 70)])
res = replai.vigiar_x("Lucia", replai.ler_conta("Lucia"), leitor2, PaginaFalsa(), escritor_falso)
check("## x" in chamadas[0] and "## linkedin" not in chamadas[0] and "Responda SÓ com um objeto JSON" in chamadas[0],
      "o pacote do vigia leva a doutrina do X e pede só o JSON")
reg = R.estados(replai.eventos("Lucia", "x"))
rasc = sorted(pid for pid, r_ in reg.items() if r_["estado"] == "rascunho")
check(res["revisao"] and len(rasc) >= 2, "modo revisão: o vigia escreve e deixa os rascunhos para o chat")
check(len(chamadas) == 2 and "Reprovados na tentativa anterior" in chamadas[1], "reprovado volta ao Claude uma vez, com o motivo")
cod, r = rodar("conta", "--rede", "x", "--modo", "sozinho")
check(cod == 2 and "rodadas revisadas" in r["erro"], "o automático não liga antes de 3 revisões limpas")
for _ in range(R.REVISOES_PARA_SOZINHO):
    replai.registrar("Lucia", "x", "revisao", n=5, editados=0, descartados=0)
cod, r = rodar("conta", "--rede", "x", "--modo", "sozinho")
check(cod == 0 and r["redes"]["x"]["modo"] == "sozinho", "depois de 3 revisões limpas, o automático liga")
replai.registrar("Lucia", "x", "aprovado", id=rasc[0])


class TelaX:
    def __init__(self):
        self.comentou, self.curtiu, self.url = {}, {}, ""

    def bloqueio(self, page):
        return None

    def controles(self, page, tid):
        return {"achou_post": True}

    def curtir(self, page, tid):
        self.curtiu[tid] = self.curtiu.get(tid, 0) + 1
        return True, "ok", "pos_clique"

    def comentar(self, page, tid, texto, meu, rng=None):
        self.comentou[tid] = self.comentou.get(tid, 0) + 1
        return True, "ok", "pos_clique"

    def respostas_na_pagina(self, page, meu, trecho=""):
        return {"da_conta": False, "link": "https://x.com/lucia/status/777" if trecho else None}


telax = TelaX()
antes = len(chamadas)
res = replai.vigiar_x("Lucia", replai.ler_conta("Lucia"), LeitorFalso([]), PaginaFalsa(), escritor_falso,
                      acoes=telax, dormir=lambda s: None)
reg = R.estados(replai.eventos("Lucia", "x"))
check(len(chamadas) == antes, "sem post novo, o Claude não é chamado (zero token)")
check(rasc[0] in telax.comentou and reg[rasc[0]]["estado"] == "comentado" and reg[rasc[0]]["link"].endswith("/777"),
      "modo sozinho: o aprovado é respondido e o link fica no registro")
check(all(n == 1 for n in telax.comentou.values()), "nenhum post respondido duas vezes")
res = replai.vigiar_x("Lucia", replai.ler_conta("Lucia"), LeitorFalso([]), PaginaFalsa(), escritor_falso,
                      acoes=telax, dormir=lambda s: None)
check(all(n == 1 for n in telax.comentou.values()), "rodar o vigia de novo não responde de novo")
check(replai.resumo_vigia({"coleta": {"posts_vistos": 3, "candidatos": 1, "no_atraso": 1},
                           "escrita_1": {"aceitos": 1}, "postagem": {"comentados": [1]}})
      == "3 vistos, 1 novos, 1 no atraso, 1 escritos, 1 respondidos", "resumo de uma linha do vigia")

print("\n== 11. ligar e desligar o vigia ==")
cmd = replai.comando_vigia("ligar")
check(cmd[:2] == ["schtasks", "/create"] and cmd[cmd.index("/tn") + 1] == "Replai vigia"
      and cmd[cmd.index("/mo") + 1] == "5" and "vigiar --todas" in cmd[cmd.index("/tr") + 1],
      "uma tarefa do Windows para o PC todo, a cada 5 min, passando pelas contas")
check(replai.comando_vigia("desligar")[:2] == ["schtasks", "/delete"], "desligar apaga a tarefa")
comandos = []
replai.rodar_comando = lambda cmd: (comandos.append(cmd), (0, ""))[1]
replai.claude_instalado = lambda: False
cod, r = rodar("vigia", "--rede", "x", "--ligar")
check(cod == 2 and "Claude Code" in r["erro"] and not comandos, "sem o Claude Code de linha de comando, não liga")
replai.claude_instalado = lambda: True
cod, r = rodar("vigia", "--rede", "x", "--ligar")
check(cod == 0 and r["vigia"] and comandos[-2][1] == "/create" and comandos[-1][0] == "powershell"
      and "AllowStartIfOnBatteries" in comandos[-1][-1], "liga, grava na conta e deixa rodar na bateria")
check(any(c_[:2] == ["schtasks", "/delete"] and c_[3] == "Replai vigia Lucia" for c_ in comandos),
      "ligar apaga a tarefa antiga desta conta (uma por conta até 12/11)")
cod, r = rodar("status")
check(r["redes"]["x"]["vigia"] and r["redes"]["x"]["ultimo_vigia"] is None, "status mostra o vigia ligado")
cod, r = rodar("vigia", "--rede", "x", "--desligar")
check(cod == 0 and not r["vigia"] and comandos[-1][1] == "/delete", "desliga")
cod, r = rodar("vigia", "--ligar")
check(r["redes_com_vigia"] == ["linkedin", "x"] and comandos[-2][1] == "/create", "sem --rede: o vigia das duas redes numa tarefa só")
cod, r = rodar("vigia", "--rede", "linkedin", "--desligar")
check(r["redes_com_vigia"] == ["x"] and comandos[-2][1] == "/create", "desligar uma rede mantém a tarefa da outra")
cod, r = rodar("vigia", "--desligar")
check(not r["redes_com_vigia"] and comandos[-1][1] == "/delete", "sem vigia em nenhuma rede, a tarefa sai")

import plistlib as _pl  # noqa: E402

_agentes = replai.PASTA_AGENTES
replai.PASTA_AGENTES = TMP / "LaunchAgents"
comandos.clear()
antigo = replai.PASTA_AGENTES / "com.replai.vigia.lucia-prado.plist"
antigo.parent.mkdir(parents=True, exist_ok=True)
antigo.write_bytes(b"x")
replai.apagar_vigia_antigo("Lúcia Prado", sistema="mac")
check(not antigo.exists() and comandos[-1][:2] == ["launchctl", "bootout"], "Mac: o agente antigo da conta sai")
cod, _ = replai.tarefa_do_vigia("ligar", sistema="mac")
plist = replai.PASTA_AGENTES / "com.replai.vigia.plist"
dado = _pl.loads(plist.read_bytes())
check(cod == 0 and dado["ProgramArguments"][-2:] == ["vigiar", "--todas"]
      and dado["StartInterval"] == R.VIGIA_TICK_MIN * 60 and ".local/bin" in dado["EnvironmentVariables"]["PATH"]
      and comandos[-1][:2] == ["launchctl", "bootstrap"],
      "Mac: o vigia é um agente do launchd a cada 5 min, com o caminho do claude no PATH")
replai.tarefa_do_vigia("consultar", sistema="mac")
check(comandos[-1][:2] == ["launchctl", "print"], "Mac: o testar confere o agente")
replai.tarefa_do_vigia("desligar", sistema="mac")
check(not plist.exists() and comandos[-1][:2] == ["launchctl", "bootout"], "Mac: desligar tira o agente")
check(replai.tarefa_do_vigia("ligar", sistema="outro")[0] != 0, "fora de Windows e Mac, o vigia não liga")
replai.PASTA_AGENTES = _agentes
chrome_mac = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--user-data-dir=/s", "about:blank"]
check(L.escondido_no_mac(chrome_mac, mac=True)[:7] == ["open", "-n", "-g", "-j", "-a", "/Applications/Google Chrome.app",
                                                       "--args"]
      and L.escondido_no_mac(chrome_mac, mac=True)[7:] == chrome_mac[1:]
      and L.escondido_no_mac(chrome_mac, mac=False) == chrome_mac,
      "Mac: o vigia abre o Chrome com o app escondido (Cmd+H), sem roubar o foco; no Windows nada muda")

print("\n== 12. lista pelo link do Google Sheets ==")
LINK = "https://docs.google.com/spreadsheets/d/1AbC-dEf_123/edit#gid=456"
check(replai.url_exportacao(LINK) == "https://docs.google.com/spreadsheets/d/1AbC-dEf_123/export?format=csv&gid=456",
      "link do Google vira o link de exportação em CSV da aba certa")
check(replai.url_exportacao("https://example.com/x") is None, "link que não é do Google")
csv_google = ("Lead,Empresa,Profile URL,Prioridade\n"
              "Dora Lins,Acme,https://www.linkedin.com/in/dora-lins/,alta\n"
              "Eli Prado,Beta,https://www.linkedin.com/in/eli-prado,\n")
baixou = []
replai.baixar_planilha = lambda url: (baixou.append(url), csv_google)[1]
cod, r = rodar("lista", "--rede", "linkedin", "--nome", "Google", "--planilha", LINK)
check(cod == 0 and r["linhas_na_planilha"] == 2 and r["lista"]["planilha"] == LINK,
      "lista pelo link: lê a planilha e acha a coluna do perfil sozinha")
pg = [p for p in replai.perfis_da_rede("Lucia", replai.ler_conta("Lucia"), "linkedin", "Google")]
check([p["chave"] for p in pg] == ["dora-lins", "eli-prado"] and pg[0]["prioridade"] == "alta",
      "os perfis vêm da planilha do Google")
n = len(baixou)
replai.perfis_da_rede("Lucia", replai.ler_conta("Lucia"), "linkedin", "Google")
check(len(baixou) == n, "dentro da hora, usa a cópia (não baixa de novo)")
replai.agora = lambda: T + timedelta(hours=2)
csv_google += "Fabi Reis,Gama,https://www.linkedin.com/in/fabi-reis/,\n"
pg = replai.perfis_da_rede("Lucia", replai.ler_conta("Lucia"), "linkedin", "Google")
check(len(baixou) == n + 1 and len(pg) == 3, "depois de uma hora, baixa de novo: quem entrou na planilha vale sozinho")


def google_fora(url):
    raise replai.Erro("Google fora do ar")


replai.baixar_planilha = google_fora
replai.agora = lambda: T + timedelta(hours=5)
check(len(replai.perfis_da_rede("Lucia", replai.ler_conta("Lucia"), "linkedin", "Google")) == 3,
      "Google fora do ar: segue com a última cópia")
replai.agora = lambda: T
rodar("lista", "--rede", "linkedin", "--nome", "Google", "--ativa", "nao")

print("\n== 13. a mesma planilha do Google para o LinkedIn e o X ==")
LINK2 = "https://docs.google.com/spreadsheets/d/2Mesma_Lista/edit"
csv2 = ("Nome,Empresa,LinkedIn,X\n"
        "Gil Souza,Acme,https://www.linkedin.com/in/gil-souza/,@gilsouza\n"
        "Iara Lima,Beta,https://www.linkedin.com/in/iara-lima/,\n"
        "Juca Reis,Gama,,https://x.com/jucareis\n")
replai.baixar_planilha = lambda url: csv2
rodar("lista", "--rede", "linkedin", "--nome", "Lucia", "--planilha", LINK2)
rodar("lista", "--rede", "x", "--nome", "Lucia", "--planilha", LINK2)
c = replai.ler_conta("Lucia")
li_ = [p["chave"] for p in replai.perfis_da_rede("Lucia", c, "linkedin", "Lucia")]
x_ = [p["chave"] for p in replai.perfis_da_rede("Lucia", c, "x", "Lucia")]
check(li_ == ["gil-souza", "iara-lima"], "LinkedIn pega a coluna LinkedIn (quem não tem fica fora)")
check(x_ == ["gilsouza", "jucareis"], "X pega a coluna X, com @ ou link (quem não tem fica fora)")
semnome = "Pessoa,Coluna A,Coluna B\nGil,https://www.linkedin.com/in/gil-souza/,@gilsouza\n"
replai.baixar_planilha = lambda url: semnome
check([d["Perfil"] for d in replai.ler_tabela(LINK2, "x")] == ["@gilsouza"]
      and [d["Perfil"] for d in replai.ler_tabela(LINK2, "linkedin")] == ["https://www.linkedin.com/in/gil-souza/"],
      "sem nome de coluna claro, cada rede acha a sua pelo conteúdo")
check(replai.ler_tabela(LINK2, "linkedin")[0].get("Nome") == "Gil",
      "a coluna 'Pessoa' vira o Nome (não cai no vanity)")
rodar("lista", "--rede", "linkedin", "--nome", "Lucia", "--ativa", "nao")
rodar("lista", "--rede", "x", "--nome", "Lucia", "--ativa", "nao")

print("\n== 14. um navegador só para as duas redes ==")
c = replai.ler_conta("Lucia")
check(replai.sessao_de("Lucia", c, "x") == replai.sessao_de("Lucia", c, "linkedin") == replai.CAMPANHA / "_navegador",
      "X e LinkedIn usam o mesmo navegador (o da campanha, quando ela existe)")
check(replai.trava_de("Lucia", c, "x") == replai.trava_de("Lucia", c, "linkedin"),
      "a trava é do navegador: as duas redes nunca abrem juntas")
check(L.comando_chrome("chrome.exe", replai.sessao_de("Lucia", c, "x"))[1]
      == f"--user-data-dir={replai.sessao_de('Lucia', c, 'linkedin')}",
      "login e robô abrem o mesmo Chrome do Replai, com a mesma pasta de sessão")

print("\n== 15. vigia do LinkedIn: notificações do sininho ==")
c = replai.ler_conta("Lucia")
T2 = T + timedelta(days=1)                       # dia seguinte: a parada da seção 6 já passou
replai.agora = lambda: T2
aid_novo = str(int((T2 - timedelta(hours=1)).timestamp() * 1000) << 22)
POST_NOVO = dict(lp("bruno-reis", "Bruno Reis", 1), activity_id=aid_novo,
                 data=L.data_da_activity(aid_novo, int(T2.timestamp() * 1000) + 1000),
                 url=L.url_do_post(f"urn:li:activity:{aid_novo}"),
                 texto="Bruno Reis conta que o banco correspondente fecha a janela de câmbio às 15h e trava a liquidação.")
voy_v = VoyFalsa({"URN-bruno-reis": [POST_NOVO]})
avisos_ = [{"vanity": "bruno-reis", "activity": POST_NOVO["activity_id"]},
           {"vanity": "de-fora", "activity": "123"}]
escritas = []


def escritor_li(pacote):
    escritas.append(pacote)
    ids = [l.split('"')[3] for l in pacote.splitlines() if l.strip().startswith('"id"')]
    return {i: "Fechar câmbio às 15h obriga quem importa insumo a antecipar a compra de dólar." for i in ids}


res = replai.vigiar_linkedin("Lucia", c, voy_v, PaginaFalsa(), escritor_li, avisos=lambda page: avisos_)
reg = R.estados(replai.eventos("Lucia", "linkedin"))
check(res["coleta"]["avisos"] == 1 and reg[POST_NOVO["activity_id"]]["estado"] == "rascunho",
      "aviso de quem está na lista vira rascunho; aviso de quem está fora é ignorado")
check("## linkedin" in escritas[0] and "Responda SÓ com um objeto JSON" in escritas[0], "escrito pelo Claude com a doutrina do LinkedIn")
n_lidas = voy_v.feitas
res = replai.vigiar_linkedin("Lucia", c, voy_v, PaginaFalsa(), escritor_li, avisos=lambda page: [])
check(res.get("coleta", {}).get("nada_a_fazer") and voy_v.feitas == n_lidas and len(escritas) == 1,
      "sem aviso novo: nenhuma leitura de perfil e nenhum Claude")
res = replai.vigiar_linkedin("Lucia", c, voy_v, PaginaFalsa(), escritor_li, avisos=lambda page: avisos_)
check(len(escritas) == 1, "o mesmo aviso de novo não traz o post de novo")

print("\n== 16. sininho nos perfis da lista ==")


class TelaSino:
    def __init__(self):
        self.vistos = []

    def ligar_sininho(self, page, url):
        self.vistos.append(url)
        if "bruno" in url:
            return "ja_estava", "desligar notificações"
        if "carla" in url:
            return "sem_botao", "sininho não achado"
        return "ligado", "desligar notificações"


tela_s = TelaSino()
res = replai.ligar_sininhos("Lucia", replai.ler_conta("Lucia"), PaginaFalsa(), acoes=tela_s, dormir=lambda s: None)
check(res["ligados"] == 1 and res["ja_estavam"] == 1 and len(res["sem_botao"]) == 1, "liga, reconhece o que já estava e aponta o que falhou")
check(res["faltam_depois"] == 1, "quem não deu certo continua na fila para a próxima vez")
antes = len(tela_s.vistos)
res = replai.ligar_sininhos("Lucia", replai.ler_conta("Lucia"), PaginaFalsa(), acoes=tela_s, dormir=lambda s: None)
check(len(tela_s.vistos) == antes, "quem falhou hoje fica para amanhã (não gasta o teto do dia)")
replai.agora = lambda: T2 + timedelta(days=1)
res = replai.ligar_sininhos("Lucia", replai.ler_conta("Lucia"), PaginaFalsa(), acoes=tela_s, dormir=lambda s: None,
                            maximo=2)
check(len(tela_s.vistos) == antes + 1 and res["tentados"] == 1, "no dia seguinte tenta de novo só quem faltou")
replai.agora = lambda: T2

print("\n== 17. as duas redes juntas: um pacote, uma revisão, postagem intercalada ==")
T3 = T2 + timedelta(hours=2)                     # a cópia da planilha do Google já venceu
replai.agora = lambda: T3
replai.baixar_planilha = lambda url: "Nome,LinkedIn\nHugo Lima,https://www.linkedin.com/in/hugo-lima/\n"
rodar("lista", "--rede", "linkedin", "--nome", "Juntas", "--planilha", "https://docs.google.com/spreadsheets/d/5Juntas/edit")
aid_h = str(int((T3 - timedelta(hours=1)).timestamp() * 1000) << 22)
POST_H = dict(lp("hugo-lima", "Hugo Lima", 1), activity_id=aid_h,
              data=L.data_da_activity(aid_h, int(T3.timestamp() * 1000) + 1000),
              url=L.url_do_post(f"urn:li:activity:{aid_h}"),
              texto="Hugo Lima diz que a janela de câmbio das 15h ainda decide o caixa de quem importa.")
voy_h = VoyFalsa({"URN-hugo-lima": [POST_H]})
TW_H = dict(tw("9401", "hugo_x", 0), data=(T3 - timedelta(minutes=40)).isoformat())


class LeitorHugo(LeitorFalso):
    def membros(self, url):
        self.feitas += 1
        return ["hugo_x"]


TXT_JUNTAS = {"linkedin": "Janela das 15h obriga a tesouraria a fechar a posição antes do almoço.",
              "x": "A 3pm cut-off forces treasury teams to pre-fund the morning before."}
pacotes = []


def escritor_juntas(pacote):
    pacotes.append(pacote)
    ids = [l.split('"')[3] for l in pacote.splitlines() if l.strip().startswith('"id"')]
    return {i: TXT_JUNTAS[i.split(":")[0]] for i in ids}


c = replai.ler_conta("Lucia")
telax2 = TelaX()
partes = {"linkedin": replai.parte_linkedin("Lucia", c, voy_h, PaginaFalsa(),
                                            avisos=lambda page: [{"vanity": "hugo-lima", "activity": aid_h}]),
          "x": replai.parte_x("Lucia", c, LeitorHugo([TW_H]), PaginaFalsa(), acoes=telax2)}
res = replai.vigiar_redes("Lucia", c, partes, escritor_juntas, dormir=lambda s: None)
check(len(pacotes) == 1, "vigia das duas redes: uma chamada só ao Claude")
check(pacotes[0].count("## comum") == 1 and "## linkedin" in pacotes[0] and "## x" in pacotes[0]
      and f'"id": "linkedin:{aid_h}"' in pacotes[0] and '"id": "x:9401"' in pacotes[0],
      "o pacote leva a doutrina comum uma vez e os ids com a rede na frente")
check(res["linkedin"]["revisao"] and telax2.comentou == {"9401": 1},
      "cada rede no modo dela: LinkedIn em revisão espera o chat, X sozinho responde")
check(replai.separar_resposta({"x:1": "a", "linkedin:2": "b", "lixo": "c"}, ["linkedin", "x"])
      == {"linkedin": {"2": "b"}, "x": {"1": "a"}}, "a resposta volta separada por rede")

cod, txt = rodar("revisao")
check(cod == 0 and "LinkedIn:" in txt and "Janela das 15h" in txt, "revisão sem --rede: as redes numa lista só")
dec2 = replai.arq("Lucia", "rodada", "decisoes.json")
replai.registrar("Lucia", "x", "selecionado", id="9501", autor="ivo_x", nome="Ivo", url="https://x.com/ivo_x/status/9501",
                 data=T3.isoformat(), trecho="post")
replai.registrar("Lucia", "x", "rascunho", id="9501", texto="Pre-funding the morning is the hidden cost of a 3pm cut-off.", voz=1)
cod, txt = rodar("revisao")
check("X:" in txt and "LinkedIn:" in txt, "rascunho do X entra na mesma revisão")
dec2.write_text(json.dumps({"todos": "ok"}), encoding="utf-8")
cod, r = rodar("aprovar", "--arquivo", str(dec2))
check(r["linkedin"]["aprovados"] >= 1 and r["x"]["aprovados"] >= 1 and not r["x"]["esperando"],
      "um 'ok' aprova as duas redes")

relog, ordem = [0.0], []


def passos_falsos(nome, pausas):
    for pz in pausas:
        ordem.append(nome)
        yield pz
    ordem.append(nome)
    return nome + " ok"


r = replai.rodar_juntos({"linkedin": passos_falsos("li", [100, 100]), "x": passos_falsos("x", [30, 30, 30])},
                        dormir=lambda s: relog.__setitem__(0, relog[0] + s), relogio=lambda: relog[0])
check(ordem == ["li", "x", "x", "x", "x", "li", "li"] and relog[0] == 200 and r == {"linkedin": "li ok", "x": "x ok"},
      "postagem intercalada: o X age nas pausas do LinkedIn (200 s em vez de 290), cada rede com a pausa dela")

replai.registrar("Lucia", "x", "vigia", resumo="teste")
replai.registrar("Lucia", "linkedin", "vigia", resumo="teste")
check(not replai.vigia_na_hora("Lucia", "x"), "a tarefa roda a cada 5 min, mas cada rede respeita o intervalo dela")
replai.agora = lambda: T3 + timedelta(minutes=8)
check(replai.vigia_na_hora("Lucia", "x") and not replai.vigia_na_hora("Lucia", "linkedin"),
      "8 min depois: o X age (10 min), o LinkedIn ainda não (15 min)")
replai.agora = lambda: T3 + timedelta(minutes=13)
check(replai.vigia_na_hora("Lucia", "linkedin"), "13 min depois: o LinkedIn age")
replai.agora = lambda: T3

print("\n== 18. Claude em segundo plano: enxuto, com volta para o simples ==")
import shutil as _sh  # noqa: E402
import subprocess as _sp  # noqa: E402
chamadas_cli, _run, _which = [], _sp.run, _sh.which


class Proc:
    def __init__(self, rc, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def run_antigo(cmd, **kw):
    chamadas_cli.append(cmd)
    if "--setting-sources" in cmd:
        return Proc(1, "", "error: unknown option '--setting-sources'")
    return Proc(0, json.dumps({"result": '{"1": "ok"}', "is_error": False}))


_sh.which, _sp.run = (lambda n: "claude"), run_antigo
try:
    check(replai.escrever_com_claude("pacote") == {"1": "ok"} and len(chamadas_cli) == 2
          and "--system-prompt" in chamadas_cli[0] and "--system-prompt" not in chamadas_cli[1],
          "tenta primeiro sem o prompt do Claude Code e sem plugins; Claude Code antigo cai no simples")
    chamadas_cli.clear()
    _sp.run = lambda cmd, **kw: (chamadas_cli.append(cmd), Proc(0, json.dumps({"result": '{"2": "ok"}'})))[1]
    check(replai.escrever_com_claude("pacote") == {"2": "ok"} and len(chamadas_cli) == 1, "Claude Code novo: uma chamada só")
finally:
    _sh.which, _sp.run = _which, _run

print("\n== 19. configurar: a primeira vez num comando ==")
replai.baixar_planilha = lambda url: ("Nome,LinkedIn,X\nLia Melo,https://www.linkedin.com/in/lia-melo/,@liamelo\n"
                                      "Rui Dias,https://www.linkedin.com/in/rui-dias/,\n")
cod, r = rodar("configurar", "--nome", "Maria Souza", "--operador", "Roger", "--idioma", "pt",
               "--redes", "linkedin,x", "--lista", "https://docs.google.com/spreadsheets/d/3Conf/edit",
               "--nunca-citar", "Acme")
cm = replai.ler_conta("Maria")
check(cod == 0 and r["perfis_por_rede"] == {"linkedin": 2, "x": 1} and not r["erros"],
      "um comando: quem opera, conta, as duas redes e a mesma planilha para as duas")
check(cm["redes"]["x"]["ativa"] and "Acme" in cm["nomes_que_nunca_cita"] and replai.operador()["nome"] == "Roger",
      "a conta nasce com as redes ligadas e os nomes ajustados")
replai.baixar_planilha = lambda url: "Nome,LinkedIn\nLia Melo,https://www.linkedin.com/in/lia-melo/\n"
cod, r = rodar("configurar", "--nome", "Teo Lins", "--lista", "https://docs.google.com/spreadsheets/d/4Conf/edit")
check(cod == 0 and not r["erros"] and any("Lista do X" in a for a in r["avisos"])
      and not replai.ler_conta("Teo")["redes"]["x"]["ativa"],
      "planilha sem coluna do X e sem Lista do X: desliga o X, avisa e pede a Lista")
cod, r = rodar("configurar", "--nome", "Ivo Reis", "--lista", "https://docs.google.com/spreadsheets/d/4Conf/edit",
               "--x-lista", "https://x.com/i/lists/123", "--perfil-linkedin", "https://www.linkedin.com/in/ivo-reis/",
               "--perfil-x", "@ivoreis")
ci = replai.ler_conta("Ivo")["redes"]
check(cod == 0 and not r["erros"] and ci["x"]["ativa"], "com a Lista do X, a planilha sem coluna do X não é erro")
check(ci["linkedin"]["perfil"].endswith("/ivo-reis/") and ci["x"]["perfil"] == "@ivoreis",
      "o perfil da conta vem de quem opera, não de quem estiver logado")
rodar("conta", "--conta", "Teo", "--rede", "x", "--ativa", "sim")     # para o testar mostrar o X sem lista

print("\n== 19b. lista em CSV local: a fonte da verdade, editada pelo Claude ==")
cod, r = rodar("configurar", "--nome", "Bia Lopes", "--redes", "linkedin,x")
cb = replai.ler_conta("Bia")
csv_bia = replai.arq("Bia", "lista.csv")
check(cod == 0 and csv_bia.exists() and all(li.get("csv") == str(csv_bia) for li in cb["listas"])
      and {li["rede"] for li in cb["listas"]} == {"linkedin", "x"},
      "conta nova sem planilha: nasce com lista.csv servindo às duas redes")
check(any("vazia" in a for a in r["avisos"]), "avisa que a lista está vazia")
cod, r = rodar("perfil", "--conta", "Bia", "--adicionar", "https://www.linkedin.com/in/lia-melo/", "@liamelo",
               "--nome", "Lia Melo", "--prioridade", "alta")
check(cod == 0 and r["feito"] == "nova" and r["ativos"] == {"linkedin": 1, "x": 1}, "perfil --adicionar com as duas redes")
pl = replai.perfis_da_rede("Bia", replai.ler_conta("Bia"), "linkedin")
px = replai.perfis_da_rede("Bia", replai.ler_conta("Bia"), "x")
check(pl and pl[0]["chave"] == "lia-melo" and pl[0]["prioridade"] == "alta" and px[0]["chave"] == "liamelo",
      "a rodada lê o CSV na hora, sem importar")
csv_bia.write_text(csv_bia.read_text(encoding="utf-8-sig") + "Rui Dias;https://www.linkedin.com/in/rui-dias/;;;;\r\n",
                   encoding="utf-8-sig")
check(len(replai.perfis_da_rede("Bia", replai.ler_conta("Bia"), "linkedin")) == 2, "linha posta no Excel vale na hora")
cod, r = rodar("perfil", "--conta", "Bia", "--pausar", "Rui Dias")
check(cod == 0 and r["feito"] == "pausada" and len(replai.perfis_da_rede("Bia", replai.ler_conta("Bia"), "linkedin")) == 1,
      "perfil --pausar (pelo nome) tira da rodada sem apagar")
cod, r = rodar("perfil", "--conta", "Bia", "--tirar", "@ninguem")
check(cod != 0 and "não achei" in r["erro"], "tirar quem não está: avisa e não mexe")
cod, r = rodar("perfil", "--conta", "Bia", "--listar", "lia")
check(cod == 0 and len(r["pessoas"]) == 1 and r["total"] == 2, "perfil --listar com busca")
cod, r = rodar("perfil", "--conta", "Maria", "--listar")
check(cod != 0 and "lista --nome Principal --csv" in r["erro"], "conta com planilha do Google: explica como passar para CSV")
cod, r = rodar("lista", "--conta", "Maria", "--nome", "Principal", "--csv")
cm = replai.ler_conta("Maria")
check(cod == 0 and r["pessoas_trazidas"] == 2 and r["perfis_ativos"] == {"linkedin": 2, "x": 1}
      and all(li.get("csv") and not li.get("planilha") for li in cm["listas"]),
      "lista --csv traz quem estava na planilha do Google (uma linha por pessoa) e vira a fonte")
cod, r = rodar("lista", "--conta", "Maria", "--nome", "Principal", "--csv")
check(cod == 0 and r["pessoas_trazidas"] == 0 and len(replai.perfis_da_rede("Maria", cm, "linkedin")) == 2,
      "rodar de novo não sobrescreve o CSV")
csv_bia.unlink()
_abrir = replai.abrir_redes
replai.abrir_redes = lambda *a, **k: (_ for _ in ()).throw(AssertionError("abriu o navegador"))
try:
    cod, r = rodar("coletar", "--conta", "Bia", "--rede", "linkedin", "--simular")
finally:
    replai.abrir_redes = _abrir
check("sumiu" in json.dumps(r, ensure_ascii=False), "CSV apagado: a rodada para e diz como recriar, sem abrir o navegador")


print("\n== 20. testar: tudo na tela, sem postar nem clicar ==")
import playwright.sync_api as _psa  # noqa: E402
import subprocess as _sp2  # noqa: E402
import x as X  # noqa: E402


class SemPW:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class CtxFalso:
    def close(self):
        pass


class VoyTodos(VoyFalsa):
    def posts(self, urn, count=10):
        self.feitas += 1
        return [POST_H]


SALVOS = {(_psa, "sync_playwright"): _psa.sync_playwright, (replai, "abrir_redes"): replai.abrir_redes,
          (L, "controles"): L.controles, (L, "bloqueio"): L.bloqueio, (L, "posts_das_notificacoes"): L.posts_das_notificacoes,
          (L, "sininho"): L.sininho, (X, "controles"): X.controles, (X, "bloqueio"): X.bloqueio,
          (replai, "escrever_com_claude"): replai.escrever_com_claude, (replai, "caminho_chrome"): replai.caminho_chrome,
          (_sp2, "Popen"): _sp2.Popen, (replai, "rodar_juntos"): replai.rodar_juntos,
          (replai, "passos_de_postar"): replai.passos_de_postar, (replai, "parte_x"): replai.parte_x,
          (replai, "parte_linkedin"): replai.parte_linkedin, (replai, "ligar_sininhos"): replai.ligar_sininhos}
voy_t = VoyTodos({})


def redes_falsas(linkedin=None, x=None, erros=None):
    abertas = {r: v for r, v in (("linkedin", linkedin), ("x", x)) if v}
    return lambda pasta, c, pw, redes, fora_da_tela=False: (CtxFalso(), abertas, dict(erros or {}))


def escreve_ok(pacote, **kw):
    replai.MODO_CLAUDE["modo"] = "enxuto"
    return {"ok": "ok"}


_psa.sync_playwright = lambda: SemPW()
L.controles = X.controles = lambda page, pid: {"achou_post": True, "like": {"achou": True}, "comentar": {"achou": True}}
L.bloqueio = X.bloqueio = lambda page: None
L.posts_das_notificacoes = lambda page: []
L.sininho = lambda page: {"achou_perfil": True, "achou_sino": True, "ligado": True}
replai.escrever_com_claude = escreve_ok
replai.abrir_redes = redes_falsas(linkedin=(PaginaFalsa(), voy_t), x=(PaginaFalsa(), LeitorHugo([TW_H])))
cod, r = rodar("testar", "--conta", "Lucia")
it = {i["o_que"]: i for i in r["itens"]}
check(cod == 0 and r["tudo_ok"] and it["LinkedIn: a conta logada é a certa"]["ok"] and it["X: ler a lista"]["ok"]
      and it["Claude Code em segundo plano (vigia)"]["detalhe"] == "respondeu (jeito enxuto)",
      "testar: conta, lista, botões, sininho e Claude conferidos, sem postar")
check(it["LinkedIn: notificações (vigia)"]["ok"] is None and it["tarefa do vigia"]["ok"] is None,
      "o que pode ser normal (nenhum aviso, vigia desligado) vira 'confira', não erro")
cod, r = rodar("testar", "--conta", "Teo")       # a planilha do Teo não tem coluna do X, e ele não tem Lista do X
it = {i["o_que"]: i for i in r["itens"]}
check(cod == 2 and it["X: lista"]["ok"] is False and it["LinkedIn: lista"]["ok"], "rede sem ninguém na lista aparece como problema")
X.controles = lambda page, pid: {"achou_post": True, "like": {"achou": True}, "comentar": {"achou": False}}
replai.abrir_redes = redes_falsas(linkedin=(PaginaFalsa(), voy_t),
                                  erros={"x": replai.Erro("o X não está logado nesta sessão: rode 'login'", 2)})
cod, r = rodar("testar", "--conta", "Lucia")
it = {i["o_que"]: i for i in r["itens"]}
check(cod == 2 and it["X: logado"]["ok"] is False and it["LinkedIn: ler a lista"]["ok"],
      "rede deslogada aparece como problema e não impede o teste da outra")
replai.abrir_redes = redes_falsas(x=(PaginaFalsa(), LeitorHugo([TW_H])))
cod, r = rodar("testar", "--conta", "Lucia", "--rede", "x")
it = {i["o_que"]: i for i in r["itens"]}
check(it["X: curtir e responder num post (sem clicar)"]["ok"] is False
      and "tela mudou" in it["X: curtir e responder num post (sem clicar)"]["detalhe"],
      "botão que sumiu da tela aparece antes de a rodada valer")

print("\n== 21. o navegador do PC ==")
_existe = os.path.exists
try:
    os.path.exists = lambda p: "brave.exe" in str(p).lower()
    check(str(L.navegador_do_pc()).lower().endswith("brave.exe"), "sem Chrome, usa o Brave do PC")
    os.path.exists = lambda p: "chrome.exe" in str(p).lower() or "brave.exe" in str(p).lower()
    check(str(L.navegador_do_pc()).lower().endswith("chrome.exe"), "com Chrome e Brave, o Chrome vem primeiro")
    os.path.exists = lambda p: False
    check(L.navegador_do_pc() is None, "sem nenhum, o Chromium do próprio Replai")
finally:
    os.path.exists = _existe

print("\n== 22. login: o Chrome do Replai, sem robô enquanto a pessoa digita ==")
import types as _types  # noqa: E402

URLS_LOGIN = [replai.URL_LOGIN["linkedin"][1], replai.URL_LOGIN["x"][1]]
ROBO = ("automation", "no-sandbox", "mock-keychain", "password-store", "remote-debugging-pipe", "disable-extensions")
cc = L.comando_chrome("chrome.exe", "C:/sessao", URLS_LOGIN, porta=False)
check(cc[1] == "--user-data-dir=C:/sessao" and cc[-2:] == URLS_LOGIN
      and not any(m in a for a in cc for m in ROBO + ("remote-debugging",)),
      "login num Chrome comum, sem a porta (com ela o Chrome se declara robô e o Google recusa)")
cr = L.comando_chrome("chrome.exe", "C:/sessao")
check(cr[:2] == cc[:2] and "--remote-debugging-port=0" in cr and cr[-1] == "about:blank"
      and not any(m in a for a in cr for m in ROBO)
      and "--window-position=-2400,-2400" in L.comando_chrome("chrome.exe", "C:/sessao", fora_da_tela=True),
      "o robô abre o mesmo Chrome na mesma pasta, com a porta e sem as opções de robô do Playwright")


class ProcLogin:
    def __init__(self, sai_sozinho_em=None):
        self.voltas, self.sai, self.parado, self.cod = 0, sai_sozinho_em, False, None

    def poll(self):
        self.voltas += 1
        if self.sai is not None and self.voltas >= self.sai:
            self.cod = 0
        return self.cod

    def terminate(self):
        self.parado, self.cod = True, 0

    def wait(self, timeout=None):
        return self.cod

    def kill(self):
        self.cod = -9


import contextlib as _cl  # noqa: E402
import sqlite3 as _sql  # noqa: E402
import time as _time  # noqa: E402

perfil_mac = TMP / "sessao-mac"
(perfil_mac / "Default" / "Network").mkdir(parents=True)
inicio = _time.time()
para_chrome = lambda t: int((t + 11644473600) * 1_000_000)  # noqa: E731
with _cl.closing(_sql.connect(perfil_mac / "Default" / "Network" / "Cookies")) as db:
    db.execute("CREATE TABLE cookies (creation_utc INTEGER, host_key TEXT, name TEXT, encrypted_value BLOB)")
    db.executemany("INSERT INTO cookies VALUES (?, ?, ?, x'00')",
                   [(para_chrome(inicio - 3600), ".www.linkedin.com", "li_at"),      # login de antes
                    (para_chrome(inicio + 5), ".x.com", "auth_token"),
                    (para_chrome(inicio + 5), ".linkedin.com", "bcookie")])
    db.commit()
check(replai.logou_desde(perfil_mac, ["linkedin", "x"], inicio) == {"x"},
      "conta só o cookie de login gravado depois de abrir a janela")
check(replai.logou_desde(TMP / "sem-sessao", ["x"], inicio) == set(), "sem banco de cookies: ninguém logou ainda")

_ld = replai.logou_desde
try:
    vez = iter([set(), {"linkedin"}, {"linkedin", "x"}])
    replai.logou_desde = lambda perfil, redes, desde: next(vez)
    p = ProcLogin()
    replai.esperar_login(p, perfil_mac, ["linkedin", "x"], mac=True, pausa=0)
    check(p.parado and next(vez, None) is None,
          "no Mac, fecha o Chrome do login quando as duas redes logaram, e não antes (não espera o Cmd+Q)")
    replai.logou_desde = lambda perfil, redes, desde: set()
    p = ProcLogin(sai_sozinho_em=2)
    replai.esperar_login(p, perfil_mac, ["linkedin", "x"], mac=True, pausa=0)
    check(not p.parado, "fechou a janela (Windows) ou Cmd+Q antes de tudo logar: só segue para a conferência")
    replai.logou_desde = lambda perfil, redes, desde: {"linkedin", "x"}
    p, suave = ProcLogin(), []
    replai.esperar_login(p, perfil_mac, ["linkedin", "x"], mac=False, pausa=0,
                         fechar=lambda pr: (suave.append(1), pr.terminate()))
    check(p.parado and suave == [1], "no Windows também fecha sozinho quando as duas redes logaram (sem forçar)")
    replai.logou_desde = lambda perfil, redes, desde: set()
    p = ProcLogin()
    replai.esperar_login(p, perfil_mac, ["linkedin", "x"], mac=False, pausa=0, limite=0,
                         fechar=lambda pr: pr.terminate())
    check(p.parado, "janela esquecida aberta: fecha em 20 minutos")
finally:
    replai.logou_desde = _ld

passos = []
_L = {n: getattr(L, n) for n in ("fechar_aberto", "abrir_chrome")}
try:
    L.fechar_aberto = lambda pw, perfil, proc=None: passos.append(("fechar", proc))
    L.abrir_chrome = lambda perfil, urls, fora_da_tela=False, exe=None, porta=True: (
        passos.append(("abrir", urls, exe, porta)) or (None, ProcLogin(sai_sozinho_em=1)))
    replai.caminho_chrome = lambda: "brave.exe"
    replai.abrir_redes = redes_falsas(linkedin=(PaginaFalsa(), voy_t),
                                      erros={"x": replai.Erro("o X não está logado nesta sessão: rode 'login'", 2)})
    cod, txt = rodar("login", "--conta", "Lucia")
finally:
    for _n, _f in _L.items():
        setattr(L, _n, _f)
fim = json.loads(txt[txt.index("{"):])
check([p[0] for p in passos] == ["fechar", "abrir"] and passos[1][1:] == (URLS_LOGIN, "brave.exe", False),
      "o login fecha um Chrome do robô esquecido e abre a janela no navegador do PC, sem a porta")
check(cod == 2 and fim["linkedin"] == "logado" and fim["x"].startswith("NÃO logado"),
      "ao fechar, confere cada rede no mesmo Chrome e diz qual não ficou logada")


class AbaCDP:
    def __init__(self):
        self.fechada = False

    def close(self):
        self.fechada = True


class ChromeCDP:
    def __init__(self, abas):
        self.contexts = [_types.SimpleNamespace(pages=abas, new_page=AbaCDP)]
        self.desconectou = self.fechou_chrome = False

    def close(self):
        self.desconectou = True

    def new_browser_cdp_session(self):
        return _types.SimpleNamespace(send=lambda metodo: setattr(self, "fechou_chrome", metodo == "Browser.close"))


class ProcCDP:
    esperou = False

    def wait(self, timeout=None):
        self.esperou = True

    def terminate(self):
        pass


da_pessoa = AbaCDP()
chrome = ChromeCDP([da_pessoa])
nav = L.ChromeDoReplai(chrome)
aba_robo = nav.new_page()
nav.close()
check(nav.pages == [aba_robo] and aba_robo.fechada and not da_pessoa.fechada and chrome.desconectou
      and not chrome.fechou_chrome,
      "Chrome do Replai já aberto: o robô usa abas novas, fecha só as dele e deixa o Chrome aberto")
inicial, pr = AbaCDP(), ProcCDP()
chrome = ChromeCDP([inicial])
nav = L.ChromeDoReplai(chrome, pr)
nav.close()
check(nav.pages == [inicial] and chrome.fechou_chrome and pr.esperou,
      "o Chrome que o robô abriu: a aba inicial é dele, e no fim fecha o Chrome inteiro e espera sair")

check(L.porta_aberta(TMP / "sem-chrome") is None, "sem Chrome do Replai aberto, sem porta")
(TMP / "chrome-fechado").mkdir()
(TMP / "chrome-fechado" / "DevToolsActivePort").write_text("1\n/devtools/browser/x")
check(L.porta_aberta(TMP / "chrome-fechado") is None, "o arquivo de um Chrome que já fechou não conta")

_os, _subp, _sock = L.os, L.subprocess, L.socket
try:
    mortos = []
    L.socket = _types.SimpleNamespace(gethostname=lambda: "Mac-do-Lucia")
    L.subprocess = _types.SimpleNamespace(
        run=lambda cmd, **kw: _types.SimpleNamespace(stdout="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
    falso = lambda alvo: _types.SimpleNamespace(  # noqa: E731
        name="posix", readlink=lambda p: alvo, kill=lambda pid, sig: mortos.append(pid),
        path=_types.SimpleNamespace(lexists=lambda p: False))
    L.os = falso("Mac-do-Lucia-4242")
    check(L.soltar_perfil(perfil_mac) and mortos == [4242], "Mac: Chrome esquecido (aberto sem a porta) segurando a sessão: pede para sair")
    L.os = falso("Outro-Mac-4242")
    check(not L.soltar_perfil(perfil_mac) and mortos == [4242], "trava de outro computador: não mexe")
    L.os = falso("Mac-do-Lucia-5151")
    L.subprocess = _types.SimpleNamespace(run=lambda cmd, **kw: _types.SimpleNamespace(stdout="/usr/bin/python3"))
    check(not L.soltar_perfil(perfil_mac) and mortos == [4242], "o número agora é de outro programa: não mexe")
finally:
    L.os, L.subprocess, L.socket = _os, _subp, _sock
check(os.name != "nt" or L.soltar_perfil(perfil_mac) is False, "no Windows não há o que soltar")

print("\n== 22b. nada de abrir e fechar abas sem parar ==")
if os.name == "nt":
    em_uso = TMP / "em-uso"
    em_uso.mkdir()
    lancou = []
    _popen = L.subprocess.Popen
    try:
        L.subprocess.Popen = lambda *a, **k: lancou.append(a) or ProcCDP()
        with open(em_uso / "lockfile", "w"):                  # como o Chrome: segura o arquivo
            check(L.perfil_em_uso(em_uso, espera_seg=1), "Windows: Chrome com a pasta aberta é detectado")
            try:
                L.abrir_chrome(em_uso, exe="chrome.exe")
                check(False, "pasta em uso: não abre outro Chrome")
            except L.ErroNavegador as e:
                check(not lancou and "janela do Chrome do Replai está aberta" in str(e),
                      "pasta em uso: não abre outro Chrome (ele só viraria mais uma aba na janela aberta)")
        check(not L.perfil_em_uso(em_uso, espera_seg=1), "fechou: a pasta fica livre")
    finally:
        L.subprocess.Popen = _popen

c = replai.ler_conta("Lucia")
replai.marcar_sessao("Lucia", "x", False)
replai.marcar_sessao("Lucia", "x", False)
caidas = [e for e in replai.eventos("Lucia", "x") if e["ev"] in ("sessao_caiu", "sessao_ok")]
check(len(caidas) == 1 and caidas[-1]["ev"] == "sessao_caiu", "a queda da sessão fica anotada uma vez só")
abriu_nav = []
replai.abrir_redes = lambda *a, **k: abriu_nav.append(a) or (CtxFalso(), {}, {})
cod, r = rodar("coletar", "--conta", "Lucia", "--rede", "x")
check(not abriu_nav and r["nada_a_fazer"].startswith("a sessão caiu"),
      "rede com a sessão caída: o robô nem abre o navegador, e diz para logar")
cod, r = rodar("vigiar", "--conta", "Lucia", "--rede", "x", "--agora")
check(not abriu_nav and r["nada_a_fazer"].startswith("a sessão caiu"), "o vigia também não abre")
replai.marcar_sessao("Lucia", "x", True)
check(not R.sessao_caida(replai.eventos("Lucia", "x")), "o login que deu certo libera a rede")
replai.abrir_redes = SALVOS[(replai, "abrir_redes")]


class CtxUmaAba:
    pages = []

    def new_page(self):
        return object()

    def close(self):
        pass


_ac, _lx = L.abrir_contexto, replai._leitor_x
try:
    L.abrir_contexto = lambda pw, perfil, fora_da_tela=False: CtxUmaAba()
    replai._leitor_x = lambda pasta, page: (_ for _ in ()).throw(replai.ErroSessao("o X não está logado"))
    _ctx, abertas, erros = replai.abrir_redes("Lucia", c, None, ["x"])
    check(not abertas and isinstance(erros["x"], replai.ErroSessao) and R.sessao_caida(replai.eventos("Lucia", "x")),
          "ao abrir e achar a rede deslogada, a queda fica anotada")
    replai._leitor_x = lambda pasta, page: "leitor"
    _ctx, abertas, erros = replai.abrir_redes("Lucia", c, None, ["x"])
    check(abertas and not R.sessao_caida(replai.eventos("Lucia", "x")), "abriu logada: a rede volta")
    _ll, escondido = replai._leitor_linkedin, []
    L.abrir_contexto = lambda pw, perfil, fora_da_tela=False: (escondido.append(fora_da_tela), CtxUmaAba())[1]
    replai._leitor_linkedin = lambda pasta, page: "leitor-li"
    _ctx, abertas, erros = replai.abrir_redes("Lucia", c, None, ["linkedin", "x"])
    check(abertas["linkedin"][0] is abertas["x"][0] and escondido == [True],
          "as duas redes na mesma aba (uma janela só), escondida depois do login")
    replai._leitor_linkedin = _ll
finally:
    L.abrir_contexto, replai._leitor_x = _ac, _lx

print("\n== 23. postar sem --rede: as duas redes na mesma execução ==")
tela_li, tela_x3 = TelaFalsa(voy_t), TelaX()


def passos_falsos_postar(pasta, c, rede, fila, page, leitor, tocar=lambda: None, **kw):
    if rede == "x":
        return replai.postar_x(pasta, c, fila, page, "lucia", {}, acoes=tela_x3, so_passos=True)
    return replai.postar_linkedin(pasta, c, fila, page, leitor, leitor.me(), acoes=tela_li, so_passos=True)


_rj = SALVOS[(replai, "rodar_juntos")]
replai.rodar_juntos = lambda passos, dormir=None, relogio=None: _rj(passos, lambda s: None)
replai.passos_de_postar = passos_falsos_postar
replai.abrir_redes = redes_falsas(linkedin=(PaginaFalsa(), voy_t), x=(PaginaFalsa(), None))
cod, r = rodar("postar", "--conta", "Lucia")
todos = list(tela_li.comentou.values()) + list(tela_x3.comentou.values())
check(set(r) == {"linkedin", "x"} and tela_li.comentou and tela_x3.comentou and all(n == 1 for n in todos),
      "uma execução posta nas duas redes, cada post uma vez só")
cod, r = rodar("postar", "--conta", "Lucia")
check(all(n == 1 for n in list(tela_li.comentou.values()) + list(tela_x3.comentou.values())),
      "rodar de novo não comenta de novo em nenhuma rede")
fila_p = [{"id": f"97{i}", "url": f"https://x.com/a/status/97{i}", "texto": "", "comentar": False, "nome": "A"}
          for i in range(3)]
pausas = list(replai.postar_x("Lucia", replai.ler_conta("Lucia"), fila_p, PaginaFalsa(), "lucia", {},
                              acoes=TelaX(), so_passos=True))
check(len(pausas) == 2 and all(R.PAUSA_CURTIDO["x"][0] <= s <= R.PAUSA_COMENTADO["x"][1] for s in pausas),
      "entre um post e outro, a pausa humana da rede (nunca zero)")

print("\n== 24. vigiar sem --rede: a execução inteira da tarefa do Windows ==")
T4 = T3 + timedelta(days=4)                      # o descanso do autor no X (3 dias) já passou
replai.agora = lambda: T4
TW_V = dict(tw("9601", "hugo_x", 0), data=(T4 - timedelta(minutes=40)).isoformat(),
            texto="Treasury teams still pre-fund Monday payroll on Friday because of the bank cut-off.")
rodar("vigia", "--conta", "Lucia", "--ligar")
replai.escrever_com_claude = lambda pacote, **kw: {
    i: "Pre-funding Monday payroll on Friday is the quiet cost nobody models in a pilot."
    for i in (l.split('"')[3] for l in pacote.splitlines() if l.strip().startswith('"id"'))}
tela_v, sinos = TelaX(), []
_px, _pl = SALVOS[(replai, "parte_x")], SALVOS[(replai, "parte_linkedin")]
replai.parte_x = lambda pasta, c, leitor, page, tocar=lambda: None: _px(pasta, c, leitor, page, acoes=tela_v, tocar=tocar)
replai.parte_linkedin = lambda pasta, c, voy, page, tocar=lambda: None: _pl(pasta, c, voy, page, avisos=lambda pg: [],
                                                                             tocar=tocar)
replai.ligar_sininhos = lambda pasta, c, page, maximo=None, **kw: (sinos.append(maximo), {
    "tentados": 1, "ligados": 1, "ja_estavam": 0, "sem_botao": [], "nao_confirmou": [], "parou": None,
    "faltam_depois": 0})[1]
replai.abrir_redes = redes_falsas(linkedin=(PaginaFalsa(), voy_t), x=(PaginaFalsa(), LeitorHugo([TW_V])))
cod, r = rodar("vigiar", "--conta", "Lucia", "--agora")
check(cod == 0 and tela_v.comentou == {"9601": 1} and r["linkedin"]["coleta"]["nada_a_fazer"],
      "vigia das duas redes: o X responde o post novo; o LinkedIn sem aviso não lê ninguém")
check(sinos == [2] and r["linkedin"]["sininhos"]["ligados"] == 1, "o vigia liga o sininho aos poucos (2 por execução)")
check(replai.ultimo_vigia("Lucia", "x") and replai.ultimo_vigia("Lucia", "linkedin")
      and replai.arq("Lucia", "vigia-x.log").exists(), "cada rede anota a execução no registro e no log")
cod, r = rodar("vigiar", "--conta", "Lucia")
check(not r, "logo depois, nenhuma rede está na hora dela: nem abre o navegador")
for (mod, nome), f in SALVOS.items():
    setattr(mod, nome, f)

print("\n== 25. instalador numa pasta vazia ==")
casa = TMP / "casa"
pr = _sp2.run([sys.executable, str(Path(replai.__file__).with_name("instalar.py")), "--so-a-skill"],  # sem pip
              env=dict(os.environ, USERPROFILE=str(casa), HOME=str(casa)), capture_output=True, text=True,
              encoding="utf-8")
d = json.loads(pr.stdout)
check(pr.returncode == 0 and d["pronto"] and (casa / ".claude/skills/replai/SKILL.md").exists()
      and (casa / ".claude/agents/replai-escritor.md").exists() and not (casa / ".claude/skills/replai/docs").exists(),
      "o instalador põe a skill e os ajudantes no lugar (sem docs nem .git)")
if (Path(replai.__file__).parent.parent / ".git").exists():       # rodando de um clone (não de um zip)
    v_ = json.loads((casa / ".claude/skills/replai/versao.json").read_text(encoding="utf-8"))
    check(len(v_["commit"]) == 40 and Path(v_["origem"], ".git").exists(),
          "instalado de um clone: anota o commit e de onde veio (para avisar de versão nova)")

print("\n== 26. lote e escrever sem --rede: o caminho do escritor na rodada ==")
for rede_, pid_ in (("linkedin", "98001"), ("x", "98002")):
    p_ = {"id": pid_, "canon": pid_, "rede": rede_, "autor": f"lote-{rede_}", "nome": f"Lote {rede_}", "headline": "",
          "texto": "Post de teste do lote combinado sobre liquidação.", "data": replai.agora().isoformat(),
          "url": f"https://exemplo/{pid_}", "fonte": "lista:t", "prioridade": "normal", "idioma": "pt"}
    replai._fechar_coleta("Lucia", rede_, R.estados(replai.eventos("Lucia", rede_)), [p_], [], 5, False)
cod, txt = rodar("lote", "--conta", "Lucia")
check('"id": "linkedin:98001"' in txt and '"id": "x:98002"' in txt and txt.count("## comum") == 1
      and "--rede" not in txt.split("Depois rode:")[1], "lote sem --rede: as duas redes num pacote só")
saida_j = replai.arq("Lucia", "rodada", "saida.json")
saida_j.write_text(json.dumps({"linkedin:98001": "Liquidar no mesmo dia útil muda o capital de giro de quem exporta.",
                               "x:98002": "-fora do tema"}), encoding="utf-8")
cod, r = rodar("escrever", "--conta", "Lucia", "--arquivo", str(saida_j))
check(r["linkedin"]["aceitos"] == 1 and r["x"]["pulados"] == 1, "escrever sem --rede devolve cada texto à sua rede")

print("\n== 26b. o robô roda escondido; o login, não ==")
_re, chamados = replai.rodar_escondido, []
replai.rodar_escondido = lambda argv: (chamados.append(argv), 0)[1]
_osn = replai.os.name
del os.environ["REPLAI_ESCONDIDO"]
try:
    replai.os.name = "nt"
    rodar("testar", "--conta", "Lucia", "--rede", "x")
    rodar("status", "--conta", "Lucia")
    os.environ["REPLAI_VISIVEL"] = "1"
    rodar("coletar", "--conta", "Lucia")
    del os.environ["REPLAI_VISIVEL"]
finally:
    replai.os.name, replai.rodar_escondido = _osn, _re
    os.environ["REPLAI_ESCONDIDO"] = "1"
check(chamados == [["testar", "--conta", "Lucia", "--rede", "x"]],
      "comando que abre o robô vai para a área escondida; status não; REPLAI_VISIVEL=1 mostra o robô")
check("login" not in replai.COM_ROBO and {"postar", "vigiar", "coletar"} <= replai.COM_ROBO,
      "o login fica visível (quem digita é a pessoa); postar, vigia e coleta escondidos")

print("\n== 27. a voz só lê o que a conta escreveu ==")
_cp = L.comentarios_proprios
L.comentarios_proprios = lambda page, vanity: []
proprio = dict(lp("lucia-prado", "Lúcia", 5), texto="Texto que o Lúcia escreveu sobre câmbio.")
de_outro = dict(lp("outra-pessoa", "Outra", 6), texto="Post de outra pessoa que apareceu na atividade.")
replai.amostra_de("Lucia", replai.ler_conta("Lucia"), "linkedin", PaginaFalsa(), VoyFalsa({"ACoAAme": [proprio, de_outro]}))
L.comentarios_proprios = _cp
am = replai.ler_json(replai.arq("Lucia", "amostra-linkedin.json"))
check(am["posts"] == ["Texto que o Lúcia escreveu sobre câmbio."],
      "post de outra pessoa no feed de atividade (repost, menção) fica fora da voz")
zoe = {"chave": "zoe-lima", "nome": "Zoe Lima", "perfil": "https://www.linkedin.com/in/zoe-lima/", "lista": "Principal",
       "prioridade": "normal"}
voy_z = VoyFalsa({"URN-zoe-lima": [lp("zoe-lima", "Zoe Lima", 7), lp("jeff-teper", "Jeff Teper", 9)]})
res = replai.coletar_linkedin("Lucia", replai.ler_conta("Lucia"), [zoe], 5, voy_z, simular=True)
autores = {p["autor"] for p in replai.ler_json(replai.pool("Lucia", "linkedin", True))["posts"]}
check(res["de_outras_pessoas"] == 1 and autores == {"zoe-lima"},
      "coleta: post de quem não está na lista (que apareceu na atividade de quem está) não entra")

print("\n== 30. material da voz: PDF, Word, MD, HTML ==")
import importlib.util as _iu  # noqa: E402
import zipfile as _zip  # noqa: E402


def pdf_minimo(texto):
    corpo = f"BT /F1 12 Tf 10 50 Td ({texto}) Tj ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 100] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(corpo)} >>\nstream\n{corpo}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(pdf))
        pdf += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(pdf)
    pdf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    return (pdf + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode("latin-1")


mat = TMP / "material-entrada"
mat.mkdir()
(mat / "bio.md").write_text("# Lúcia\n\nCFO da   Acme.\n\n\n", encoding="utf-8")
(mat / "site.html").write_text("<html><head><style>.x{color:red}</style><script>var a = 1</script></head>"
                               "<body><h1>Quem somos</h1><p>Tesouraria&nbsp;para empresas</p></body></html>",
                               encoding="utf-8")
with _zip.ZipFile(mat / "apresentacao.docx", "w") as z:
    z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
               "<w:body><w:p><w:r><w:t>Primeira linha</w:t></w:r></w:p><w:p><w:r><w:t>Segunda </w:t></w:r>"
               "<w:r><w:t>linha</w:t></w:r></w:p></w:body></w:document>")
(mat / "artigo.pdf").write_bytes(pdf_minimo("Cambio e caixa"))
(mat / "planilha.odt").write_text("x", encoding="utf-8")
check(replai.texto_de_arquivo(mat / "bio.md") == "# Lúcia\nCFO da Acme.", "MD: texto sem linhas em branco")
check(replai.texto_de_arquivo(mat / "site.html") == "Quem somos\nTesouraria para empresas",
      "HTML: só o texto, sem script nem estilo")
check(replai.texto_de_arquivo(mat / "apresentacao.docx") == "Primeira linha\nSegunda linha", "Word: um parágrafo por linha")
tem_pypdf = _iu.find_spec("pypdf") is not None
try:
    pdf_txt = replai.texto_de_arquivo(mat / "artigo.pdf")
    check(tem_pypdf and "Cambio e caixa" in pdf_txt, "PDF: o texto das páginas")
except replai.Erro as e:
    check(not tem_pypdf and "pypdf" in str(e) and "instalador" in str(e), "PDF sem a biblioteca: manda rodar o instalador")
arquivos = [mat / n for n in ("bio.md", "site.html", "apresentacao.docx", "planilha.odt", "sumiu.pdf")]
cod, r = rodar("material", "--conta", "Lucia", *[a for f in arquivos for a in ("--arquivo", str(f))])
check(cod == 0 and [x["arquivo"] for x in r["lidos"]] == ["bio.md", "site.html", "apresentacao.docx"]
      and len(r["erros"]) == 2 and any("não achei" in e for e in r["erros"])
      and any("formato" in e for e in r["erros"]), "material: guarda o que leu e diz o que não leu, sem parar")
replai.gravar_json(replai.arq("Lucia", "amostra-linkedin.json"), {"posts": ["Post do Lúcia."], "comentarios": []})
cod, pacote = rodar("voz-pacote", "--conta", "Lucia", "--rede", "linkedin", "--tipo", "retrato")
check("Material que quem opera mandou" in pacote and "Tesouraria para empresas" in pacote
      and pacote.index("Post do Lúcia.") < pacote.index("Material que quem opera mandou"),
      "o material entra no pacote da voz, depois do que a conta escreveu")

print("\n== 31. o registro é lido aos pedaços ==")
reg_t = replai.registro_de("Leitura", "x")
replai.registrar("Leitura", "x", "leitura", n=1)
replai.registrar("Leitura", "x", "leitura", n=2)
check([e["n"] for e in replai.eventos("Leitura", "x")] == [1, 2], "lê o registro")
replai.registrar("Leitura", "x", "leitura", n=3)
check([e["n"] for e in replai.eventos("Leitura", "x")] == [1, 2, 3], "o que entrou depois aparece")
with open(reg_t, "a", encoding="utf-8") as fh:
    fh.write('{"ev": "leitura", "n": 4}')                       # linha ainda sem o fim
check([e["n"] for e in replai.eventos("Leitura", "x")] == [1, 2, 3, 4], "a linha pela metade aparece")
with open(reg_t, "a", encoding="utf-8") as fh:
    fh.write('\n{"ev": "leitura", "n": 5}\n')
check([e["n"] for e in replai.eventos("Leitura", "x")] == [1, 2, 3, 4, 5], "e não se repete quando termina")
novo_t = reg_t.with_suffix(".novo")
novo_t.write_text('{"ev": "leitura", "n": 9}\n' * 8, encoding="utf-8")
os.replace(novo_t, reg_t)
check([e["n"] for e in replai.eventos("Leitura", "x")] == [9] * 8, "arquivo trocado: lê de novo do começo")

print("\n== 33. cópia de segurança dos dados ==")
import dados as D  # noqa: E402

base_c = TMP / "dados-copia"
(base_c / "Ana" / "registro").mkdir(parents=True)
(base_c / "Ana" / "navegador").mkdir()
(base_c / "Ana" / "rodada" / "linkedin" / "falhas").mkdir(parents=True)
(base_c / "operador.json").write_text('{"nome": "Ana"}', encoding="utf-8")
(base_c / "Ana" / "conta.json").write_text('{"nome": "Ana Lima"}', encoding="utf-8")
(base_c / "Ana" / "voz-x.md").write_text("# Voz", encoding="utf-8")
(base_c / "Ana" / "registro" / "x.jsonl").write_text('{"ev": "confirmado"}\n', encoding="utf-8")
(base_c / "Ana" / "navegador" / "Cookies").write_text("segredo", encoding="utf-8")
(base_c / "Ana" / "cache-x.json").write_text("{}", encoding="utf-8")
(base_c / "Ana" / "rodada" / "linkedin" / "falhas" / "a.png").write_text("x", encoding="utf-8")
feita = D.fazer_copia(base_c, "teste")
import zipfile as _zf  # noqa: E402
nomes_zip = set(_zf.ZipFile(feita["arquivo"]).namelist())
check({"operador.json", "Ana/conta.json", "Ana/voz-x.md", "Ana/registro/x.jsonl"} <= nomes_zip
      and not any(n.startswith(("Ana/navegador", "Ana/rodada")) or "cache-" in n for n in nomes_zip),
      "a cópia leva conta, voz e registro; a sessão do navegador, a rodada e os caches ficam de fora")
shutil.rmtree(base_c / "Ana")
(base_c / "operador.json").unlink()
r = D.restaurar(base_c, feita["arquivo"])
check(r["contas_restauradas"] == ["Ana"] and (base_c / "Ana" / "registro" / "x.jsonl").exists()
      and (base_c / "operador.json").exists(), "pasta apagada: a cópia põe tudo de volta")
(base_c / "Ana" / "voz-x.md").write_text("# Voz nova", encoding="utf-8")
r = D.restaurar(base_c, feita["arquivo"])
check(r["ja_existiam"] == ["Ana"] and (base_c / "Ana" / "voz-x.md").read_text(encoding="utf-8") == "# Voz nova",
      "conta que já existe fica como está (sem --substituir)")
r = D.restaurar(base_c, feita["arquivo"], substituir=True)
check((base_c / "Ana" / "voz-x.md").read_text(encoding="utf-8") == "# Voz"
      and any("antes-de-restaurar" in c for c in D.copias(base_c)),
      "com --substituir, volta a da cópia e a atual vira uma cópia antes")
for _ in range(D.GUARDAR + 3):
    D.fazer_copia(base_c, "x")
check(len(D.copias(base_c)) <= D.GUARDAR, "guarda só as cópias mais recentes")
check(D.fazer_copia(TMP / "vazia") is None, "sem dado nenhum, não faz cópia")

print("\n== 32. o claude fora do PATH ==")
_which, _local = shutil.which, os.environ.get("LOCALAPPDATA")
try:
    shutil.which = lambda nome: None
    os.environ["LOCALAPPDATA"] = str(TMP / "LocalAppData")
    pacote_w = TMP / "LocalAppData" / "Microsoft" / "WinGet" / "Packages" / "Anthropic.ClaudeCode_x"
    pacote_w.mkdir(parents=True)
    (pacote_w / "claude.exe").write_text("", encoding="utf-8")
    check(replai.caminho_claude() == str(pacote_w / "claude.exe") and replai.claude_instalado(),
          "winget sem atalho no PATH: o vigia acha o claude na pasta do pacote")
finally:
    shutil.which = _which
    if _local is not None:
        os.environ["LOCALAPPDATA"] = _local

print("\n== 34. timeouts e telas lentas (revisão de 05/11) ==")


class TelaLenta:
    """O post só monta na terceira olhada."""

    def __init__(self):
        self.vezes = 0

    def controles(self, page, pid):
        self.vezes += 1
        return {"achou_post": self.vezes >= 3}


class PaginaEspera:
    def __init__(self):
        self.esperas = 0

    def wait_for_timeout(self, ms):
        self.esperas += 1


pg = PaginaEspera()
check(replai._post_na_tela(pg, TelaLenta(), "1") and pg.esperas == 2, "post que monta devagar: espera e acha")
check(not replai._post_na_tela(PaginaEspera(), type("Nunca", (), {"controles": lambda s, p, i: {}})(), "1"),
      "post que nunca monta: desiste depois das tentativas")


class TimeoutError_(Exception):
    pass


TimeoutError_.__name__ = "TimeoutError"


def cai(*a):
    raise TimeoutError_("Timeout 30000ms exceeded.\n=========================== logs")
    yield 1


def anda():
    yield 0
    return {"comentados": [{"nome": "ok"}]}


res = replai.rodar_juntos({"x": cai(), "linkedin": anda()}, dormir=lambda s: None)
check(res["x"]["erro"].startswith("a página demorou demais") and "logs" not in res["x"]["erro"]
      and res["linkedin"]["comentados"], "timeout numa rede vira erro dela e não derruba a outra")
e = replai.erro_inesperado(ValueError("x"))
check(isinstance(e, replai.Erro) and e.codigo == 2 and "ValueError" in str(e), "erro estranho vira Erro com o tipo")
_status = replai.cmd_status
replai.cmd_status = lambda args: (_ for _ in ()).throw(TimeoutError_("Timeout 30000ms exceeded."))
cod, r = rodar("status")
replai.cmd_status = _status
check(cod == 2 and "demorou demais" in r["erro"], "erro fora do Replai sai como JSON (o vigia escondido não tem console)")


class TelaRespostas:
    def __init__(self, resp):
        self.resp = resp

    def respostas_na_pagina(self, page, meu, trecho=""):
        return self.resp


check(replai.ja_respondido_x(None, "eu", set(), {"id": "1"}, TelaRespostas({"erro": "Error: página fechou"})),
      "X: leitura da página falhou = sem prova, não responde (regra nº 1)")
check(replai.ja_respondido_x(None, "eu", set(), {"id": "1"}, TelaRespostas({"da_conta": False})) is None,
      "X: leitura limpa libera")
import linkedin as L2  # noqa: E402
check("não ficou pronto" in L2.motivo_do_erro(Exception("waiting for element to be visible, enabled and stable")),
      "o motivo do timeout diz que o botão não ficou pronto (não que sumiu)")

print("\n== 35. aviso de versão nova (clone do GitHub) ==")


def g_(pasta, *a):
    return _sp2.run(["git", "-C", str(pasta), *a], capture_output=True, text=True, check=True).stdout.strip()


remoto, clone, outro = TMP / "remoto.git", TMP / "clone", TMP / "outro"
_sp2.run(["git", "init", "--bare", "-q", "-b", "main", str(remoto)], check=True)
_sp2.run(["git", "clone", "-q", str(remoto), str(outro)], check=True, capture_output=True)
for k, v in (("user.name", "t"), ("user.email", "t@t")):
    g_(outro, "config", k, v)
(outro / "a.txt").write_text("1", encoding="utf-8")
g_(outro, "add", "-A")
g_(outro, "commit", "-q", "-m", "primeira")
g_(outro, "push", "-q", "origin", "HEAD:main")
_sp2.run(["git", "clone", "-q", str(remoto), str(clone)], check=True, capture_output=True)
_versao = replai.VERSAO
replai.VERSAO = TMP / "versao.json"
replai.VERSAO.write_text(json.dumps({"commit": g_(clone, "rev-parse", "HEAD"), "origem": str(clone)}), encoding="utf-8")
cod, r = rodar("atualizacao")
check(cod == 0 and r["atualizar"] is False and not r["novidades"], "sem commit novo na main: nada a atualizar")
(outro / "a.txt").write_text("2", encoding="utf-8")
g_(outro, "commit", "-q", "-am", "Conserta o login no Mac")
g_(outro, "push", "-q", "origin", "HEAD:main")
cod, r = rodar("atualizacao")
check(r["atualizar"] is True and r["novidades"] == ["Conserta o login no Mac"],
      "commit novo na main: avisa e diz o que mudou")
replai.VERSAO.write_text(json.dumps({"commit": "x" * 40, "origem": str(TMP / "nao-existe")}), encoding="utf-8")
cod, r = rodar("atualizacao")
check(cod == 0 and r["atualizar"] is None, "instalado sem o clone: não avisa nada (e não quebra)")
replai.VERSAO = _versao

print("\n== 30. várias contas num PC: o vigia passa por uma de cada vez ==")
for nome_ in replai.contas():
    c_ = replai.ler_conta(nome_)
    for r_ in c_["redes"].values():
        r_["vigia"] = False
    c_["redes"]["linkedin"]["vigia"] = nome_ in ("Maria", "Ivo")
    replai.gravar_conta(nome_, c_)
abertos, ordem = [0], []
_vc = replai.vigiar_conta


def vigiar_falso(pasta, c, args):
    abertos[0] += 1
    check(abertos[0] == 1, f"{pasta}: nenhum outro navegador do Replai aberto junto")
    ordem.append(pasta)
    abertos[0] -= 1
    return {"linkedin": {"nada_a_fazer": "teste"}}


replai.vigiar_conta = vigiar_falso
comandos.clear()
cod, r = rodar("conta", "--conta", "Ivo", "--ativa", "nao")
check(cod == 0 and replai.ler_conta("Ivo")["ligada"] is False, "conta --ativa nao (sem --rede) desliga a conta inteira")
check(comandos and comandos[-2][1] == "/create", "com outra conta ainda com vigia, a tarefa do PC continua")
cod, r = rodar("vigiar", "--todas")
check(cod == 0 and ordem == ["Maria"] and "Ivo" not in r, "vigiar --todas: só as contas ligadas com vigia, uma por vez")
rodar("conta", "--conta", "Ivo", "--ativa", "sim")
ordem.clear()
rodar("vigiar", "--todas")
check(ordem == ["Ivo", "Maria"], "religada, a conta volta para a vez dela")
(replai.BASE / ".vigia.lock").write_text("outro", encoding="utf-8")
ordem.clear()
cod, r = rodar("vigiar", "--todas")
check(cod == 0 and not ordem and "ainda" in r["nada_a_fazer"], "vigia anterior ainda rodando: este pula (sem segundo navegador)")
(replai.BASE / ".vigia.lock").unlink()
replai.vigiar_conta = _vc
cod, r = rodar("contas")
ct = {x["conta"]: x for x in r["contas"]}
check(cod == 0 and {"Maria", "Ivo", "Bia"} <= set(ct) and ct["Maria"]["redes"]["linkedin"]["vigia"]
      and ct["Maria"]["lista"].endswith("lista.csv") and r["vigia_do_pc"], "contas: o painel de todas as contas do PC")
for nome_ in ("Maria", "Ivo"):
    rodar("conta", "--conta", nome_, "--ativa", "nao")
check(comandos[-1][1] == "/delete", "nenhuma conta ligada com vigia: a tarefa do PC sai")

print("\n== 33. 403 em sequência: sessão caída pede login; sessão viva é pausa curta, não o dia ==")


class VoyRecusa(VoyFalsa):
    page = None

    def urn_do_perfil(self, vanity):
        self.feitas += 1
        raise L.VoyagerErro(L.ERRO_BLOQUEIO, "perfil: LinkedIn respondeu 403", 403)


cm = replai.ler_conta("Maria")
pm = replai.perfis_da_rede("Maria", cm, "linkedin")
_expirada = L.sessao_expirada
try:
    L.sessao_expirada = lambda page: False
    try:
        replai.coletar_linkedin("Maria", cm, pm, 8, VoyRecusa({}))
        check(False, "sessão viva: 403 seguidos viram pausa curta")
    except replai.Erro as e:
        evs = replai.eventos("Maria", "linkedin")
        check(e.codigo == 4 and "PAUSA" in str(e) and not any(x["ev"] == "parada" for x in evs),
              "sessão viva: 403 seguidos viram pausa curta (sem parar a rede no dia)")
        t0 = replai.agora()
        cot = R.cotas("linkedin", t0, evs)
        check(cot["comentarios"] == 0 and "pausa até" in cot["motivo"], "durante a pausa a cota fica zerada, com o horário")
        check(R.pausa_de_leitura(evs, t0 + timedelta(minutes=R.PAUSA_LEITURA_MIN + 1)) is None
              and not R.situacao_paradas(evs, t0)[0], "passada a pausa, a rede volta sozinha no mesmo dia")
    L.sessao_expirada = lambda page: True
    try:
        replai.coletar_linkedin("Maria", cm, pm, 8, VoyRecusa({}))
        check(False, "sessão caída: pede login")
    except replai.ErroSessao as e:
        check("login" in str(e) and R.sessao_caida(replai.eventos("Maria", "linkedin")),
              "403 seguidos com a sessão caída: pede login (foi o caso de 12/11), não pausa")
finally:
    L.sessao_expirada = _expirada

shutil.rmtree(TMP, ignore_errors=True)
print(f"\nOK: {_ok} | FALHOU: {_fail}")
sys.exit(1 if _fail else 0)
