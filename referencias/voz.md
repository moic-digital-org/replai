# Voz: criar, recalibrar e aprender

A voz de cada rede mora em `Documentos\Replai\<Conta>\voz-<rede>.md`, escrita no idioma de quem
opera. É a mesma pessoa nas duas redes; muda a forma (tamanho, tom, emoji). Quem grava é sempre o
comando `voz`. Os subagentes escrevem em `rascunho-voz-<rede>.md` na mesma pasta.

**Nenhuma voz é gravada sem o ok de quem opera**: a primeira, a recalibrada e as regras aprendidas.

## Criar (as redes ligadas de uma vez, rápido)

A primeira versão sai de três fontes: 5 perguntas, o que a conta já escreveu e, se houver, arquivos
sobre a pessoa ou a empresa. Ela não precisa sair perfeita: a primeira rodada, aprovada por quem
opera, corrige o resto e ensina a voz.

1. **Leitura e perguntas ao mesmo tempo.** Rode `voz-amostra` (segundo plano) e, enquanto ele lê,
   pergunte numa mensagem só:
   1. Como a pessoa soa: mais calorosa, neutra ou mais seca? Com humor ou sem? Muda do LinkedIn
      para o X?
   2. Os assuntos em que ela tem autoridade e os que ela evita em público.
   3. Palavras ou expressões que ela usa sempre, e as que nunca usaria.
   4. Até onde ela discorda em público (evita, ou discorda com educação e argumento)?
   5. Dois ou três comentários que ela escreveria (pode colar comentários reais dela).

   E acrescente: "Se tiver material sobre ela ou a empresa (bio, apresentação, artigo, página do
   site), mande o arquivo: PDF, Word, MD ou HTML. É opcional." Arquivo arrastado para o chat vira o
   caminho dele.
2. **Material.** Para cada arquivo: `material --arquivo "<caminho>"` (vários `--arquivo` num comando
   só). `erros`: diga numa linha e siga sem ele.
3. **Voz numa passada.** Com o `voz-amostra` terminado e as respostas na mão, chame o subagente
   `replai-voz` com: "criar, conta <Conta>, python: <$PY>, script: <caminho do replai.py>" e as
   respostas coladas.
4. **Ok de quem opera.** Mostre os traços em até 6 linhas e pergunte: "Parece <Nome>? Responda ok ou
   diga o que ajustar." Ajuste pedido: edite o rascunho você mesmo (mudança pequena) e mostre de novo.
   Com o ok, grave cada rede: `voz --rede linkedin --arquivo <rascunho-voz-linkedin.md>` e
   `voz --rede x --arquivo <rascunho-voz-x.md>`, e siga para a primeira rodada (`configurar.md`,
   passo 5).

Se o `voz-amostra` der erro numa rede (sessão caída), resolva com `login` e rode de novo antes do
passo 3. Se uma rede vier com menos de 5 textos, tudo bem: as respostas e o material pesam mais.

## Recalibrar (`/replai voz`)

Mesmo roteiro do "Criar", com uma diferença: antes de gravar, mostre o que mudou em até 6 linhas e
espere o ok (só então `voz`). A voz atual entra no pacote e as perguntas são sobre o que mudou. Para
uma rede só, passe `--rede` em `voz-amostra` e diga a rede ao `replai-voz`. Material novo:
`material` de novo (um arquivo com o mesmo nome substitui o anterior).

## Aprender com a revisão

Quando o `aprovar` devolver `aprendizados_desde_a_voz` maior ou igual a 3 numa rede, ao fechar a
revisão:

1. Chame `replai-voz` com "aprendizado, conta <Conta>, rede <rede>, python: <$PY>, script: <caminho>".
2. Mostre as regras propostas numa lista curta. Quem opera responde "ok", "só a 1 e a 3" ou corrige.
3. Ajuste o rascunho se ela pediu (edição pequena, você mesmo) e rode `voz --rede <rede> --arquivo
   <rascunho>`.

`novas_proibidas` só se mostra, numa linha ("a partir de agora o Replai não usa: x, y"). Para
liberar uma: `conta --rede <rede> --ignorar-proibida <palavra>`.
