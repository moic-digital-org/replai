# Comandos do dia a dia

## Listas, nomes, modo e tetos

| Pedido | Comando |
|---|---|
| **lista em CSV (o padrão)** | `lista --nome Principal --csv` cria `Documentos\Replai\<Conta>\lista.csv` com quem já estava na lista (ou `--csv --excel "<arquivo>"` a partir de um Excel/CSV). Um arquivo serve às duas redes (colunas Nome; LinkedIn; X; Prioridade; Incluir; Observação), abre no Excel e vale na rodada seguinte |
| pôr alguém na lista | `perfil --adicionar "<link do LinkedIn>" "<@ do X>" --nome "<Nome>" [--prioridade alta] [--obs "<nota>"]` (uma rede só também vale; o mesmo perfil não duplica) |
| tirar alguém | `perfil --tirar "<link, @ ou nome>"` |
| pausar / voltar alguém | `perfil --pausar "<link, @ ou nome>"` / `perfil --retomar ...` (a linha fica, com Incluir = Não) |
| ver a lista | `perfil --listar` (ou `perfil --listar "<busca>"`); mostre nome e redes, nunca o JSON |
| lista a partir da planilha do Google | `lista --rede <rede> --nome <Nome> --planilha "<link>"` (relida a cada hora; a mesma planilha serve às duas redes) |
| lista a partir de um Excel | `lista --rede <rede> --nome <Nome> --excel "<arquivo>"` |
| lista do X a partir de uma Lista do X | `lista --rede x --nome <Nome> --x-lista "https://x.com/i/lists/..."` |
| mais perfis (lista do Google) | é só pôr a linha na planilha (vale na hora seguinte); para editar pela conversa, passe para CSV |
| tirar alguém (lista do Google) | apaga a linha ou põe Incluir = Não; no X, tira da Lista |
| prioridade de uma lista | `lista --rede <rede> --nome <Nome> --prioridade alta` |
| pausar uma lista | `lista --rede <rede> --nome <Nome> --ativa nao` |
| nome que a conta nunca cita | `conta --nunca-citar "<Nome>"` (ou `--pode-citar "<Nome>"` para liberar) |
| todas as contas do PC | `contas` (uma linha por conta, sem JSON) |
| ligar ou desligar uma conta inteira | `conta --conta <Conta> --ativa sim` (ou `nao`): desligada, nem o vigia passa por ela |
| soltar a parada de hoje | `liberar --rede <rede> [--motivo "<por quê>"]`, só quando quem opera pedir com todas as letras (por exemplo, uma parada que não era bloqueio). Fica no registro; captcha de verdade não se libera |
| ligar ou desligar uma rede | `conta --rede <rede> --ativa sim` (ou `nao`) |
| revisão ou sozinho | `conta --rede <rede> --modo revisao` (ou `sozinho`, que só liga depois de 3 rodadas revisadas sem correção) |
| mudar o teto do dia (mais ou menos) | `conta --rede <rede> --teto-comentarios N --teto-curtidas N`, até o máximo (LinkedIn 40 e 80; X 30 e 60); acima disso o script grava o máximo |
| liberar palavra proibida | `conta --rede <rede> --ignorar-proibida <palavra>` |
| idioma da conversa e da planilha | `operador --idioma en` (ou `pt`) |
| versão nova do Replai? | `atualizacao` (compara com a main do GitHub e lista as novidades); `atualizacao --aplicar` atualiza e reinstala, só com o ok |
| cópia de segurança dos dados | `copia` (faz uma agora e lista as que há; o instalador faz uma antes de cada atualização). Ficam em `Documentos\Replai\_copias` |
| pasta de dados apagada | `restaurar` (a cópia mais recente). Conta que já existe fica como está, a não ser com `--substituir`. Depois, `login` |
| PC novo | instalar, e `restaurar --arquivo "<zip>"` com o zip trazido do `_copias` do PC antigo. Depois, `login` |


## Ritmo ("por que saem poucos comentários?")

Responda com o que a última rodada mostrou (`fora` do `coletar`, `cota_agora` do `status`), em poucas linhas:

- **Aquecimento** (`regra.AQUECIMENTO`): 40% do teto nos 7 primeiros dias desde a primeira ação, 70% até o 14º.
- **Fim de semana** e **duas paradas em 7 dias**: metade cada. **Por hora** = por rodada (LinkedIn 10, X 8).
- **Janela** (`JANELA_H`): 14 dias no LinkedIn e 48 h no X; as primeiras 24 h (LinkedIn) e 6 h (X) têm preferência.
- **Um post por autor na rodada** e **descanso do autor** (7 dias no LinkedIn, 3 no X).
- No X, a maior parte do que se lê é resposta a post de outro (fica fora).
- O escritor pula o que não tem o que acrescentar.

Mais volume: teto no máximo, rodada de manhã nas duas redes e o vigia depois das 3 rodadas limpas.

## Cartão de ajuda (`/replai help`)

Mostre no idioma de quem opera:

    Replai: comenta nos posts da sua lista, na voz da conta, no LinkedIn e no X, e posta sozinho.

      /replai              placar de hoje e o que espera por você
      /replai rodar        rodada agora nas duas redes (lê, escreve, você revisa, ele posta)
      /replai simular      mostra o que faria; nada é postado
      /replai aprovar      os comentários esperando sua revisão
      /replai vigia        liga/desliga o vigia (responde minutos depois do post)
      /replai voz          ajusta a voz da conta
      /replai lista        quem a conta comenta: "põe fulano", "tira fulano", "pausa fulano"
      /replai status       números e situação de cada rede
      /replai testar       confere se está tudo funcionando, sem postar

    Revisão: "ok" aprova todos · "3: texto" troca · "tira 5" descarta · "5: motivo" ensina
    Limites: o Replai cuida sozinho (aquecimento da conta, teto por dia, horário, pausas)
    Lista: Documentos > Replai > <Conta> > lista.csv (abre no Excel)
    Relatório: Documentos > Replai > <Conta> > Replai - <Conta>.xlsx
    Seus dados ficam em Documentos > Replai e passam por toda atualização: não apague essa pasta.
    Um PC opera várias contas; cada conta roda num PC só.
