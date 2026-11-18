# Replai: instalar e usar

O Replai comenta nos posts das pessoas da sua lista, no LinkedIn e no X, com a voz da conta (a do
Lúcia, por exemplo). Ele lê, escreve, você revisa e ele posta. O **vigia** responde poucos minutos
depois de alguém da lista postar. Você conversa com ele pelo app do Claude, em português ou inglês.


> **Aviso / Disclaimer.** O Replai automatiza ações numa conta pessoal do LinkedIn e do X (ler posts, curtir e
> comentar). Os termos de uso das duas redes restringem automação e podem levar a limite, verificação,
> suspensão ou banimento da conta. Use por sua conta e risco, só em contas que você opera com autorização,
> e respeite os termos de cada rede e as leis aplicáveis, inclusive de proteção de dados. O Replai não é
> afiliado ao LinkedIn, ao X nem à Anthropic, e é distribuído "no estado em que se encontra", sem garantia
> (licença MIT, em `LICENSE`). Os tetos e pausas do script reduzem o risco, mas não o eliminam.

## Antes de começar (separe 1 hora a 1h30)

- **O PC que fica ligado durante o dia.** A conta roda num PC só: se você opera a conta de outra
  pessoa, só um de vocês instala o Replai para ela.
- **O app do Claude** instalado e com a sua conta.
- **A pessoa da conta disponível no celular.** Você vai entrar no LinkedIn e no X dela uma vez; se a
  rede pedir código, ela recebe e passa para você na hora.
- **O link do perfil da conta** no LinkedIn e o @ dela no X.
- **O link da planilha do Google** com as pessoas (o nome e o link do perfil de cada uma; para o X, uma
  coluna com o @ ou o link do X). Compartilhada como **"qualquer pessoa com o link pode ver"**. Se
  existir uma **Lista do X** (`https://x.com/i/lists/...`), o link dela também.

## Instalar (uns 5 minutos)

1. Abra o app do **Claude** e vá na aba **Code**.
2. Se ele pedir uma pasta, escolha **Documentos**.
3. Escreva (copie e cole):
   **instala o Replai: clone https://github.com/moic-digital-org/replai e siga o README**
4. Quando ele pedir permissão, clique em **Permitir**.
5. Se abrir uma janela do GitHub, entre com a sua conta e clique em **Authorize**.
6. Quando ele disser "Pronto", abra uma **conversa nova** e digite **`/replai`**.

Sem o Claude (só no Windows): no link acima, clique em **Code > Download ZIP**, descompacte e dê dois
cliques em `instalar.bat`. Se aparecer o aviso azul do Windows, clique em **Mais informações** e
depois em **Executar assim mesmo**.

## A primeira vez com o `/replai`

1. **Perguntas, numa mensagem só.** Responda tudo de uma vez: o seu nome, de quem é a conta e as redes,
   o link do perfil e o @, o link da planilha e os nomes que a conta nunca cita.
2. **Login, uma vez só.** Abre uma janela com uma aba do LinkedIn e uma do X. Entre na conta em cada
   aba (pode ser com o Google da pessoa da conta) e, quando as duas estiverem no feed, avise no chat:
   o Replai fecha a janela para você e, daí em diante, roda escondido. Você não precisa fechar nada.
3. **Voz.** Responda as 5 perguntas sobre como a pessoa escreve. Se tiver material dela ou da empresa
   (bio, apresentação, artigo), arraste o arquivo: é opcional. Ele mostra um resumo da voz: responda
   **ok** ou diga o que ajustar.
4. **Primeira rodada.** Ele mostra os comentários numerados e você revisa (veja "Como revisar"). Ele
   posta **um** por rede e manda os links: abra e confira. Se estiver certo, responda ok e ele posta o
   resto.
5. **Vigia.** Abre uma página do Claude no navegador: entre com a sua conta e clique em **Autorizar**
   (uma vez só). A partir daí ele escreve sozinho quando alguém da lista posta e guarda para você
   aprovar com `/replai aprovar`.

Depois de **3 rodadas seguidas sem você precisar corrigir**, ele pergunta se pode postar sem a sua
revisão. Antes disso, ele não posta nada sem você aprovar.

## No dia a dia

| Você digita | O que acontece |
|---|---|
| `/replai` | o placar de hoje e o que está esperando você |
| `/replai aprovar` | os comentários esperando a sua revisão (das duas redes, numa lista só) |
| `/replai rodar` | uma rodada agora nas duas redes: lê, escreve, você revisa, ele posta |
| `/replai vigia` | liga ou desliga o vigia |
| `/replai voz` | ajusta a voz da conta |
| `/replai lista` | troca ou acrescenta uma lista (para pôr ou tirar gente, mexa direto na planilha) |
| `/replai testar` | confere se está tudo funcionando, sem postar |
| `/replai help` | o cartão de comandos |

**Como revisar.** Ele mostra os comentários numerados, separados por rede. Responda:

- **ok**: aprova todos;
- **3: texto novo**: troca o comentário 3 pelo seu texto;
- **tira 5**: descarta o 5;
- **5: formal demais**: descarta o 5 e ensina o motivo.

Cada correção ensina o Replai. Você pode voltar para a revisão quando quiser.

**A planilha** fica em **Documentos > Replai > (conta) > Replai - (conta).xlsx**: as listas, tudo o
que ele curtiu e comentou, e um resumo. Na coluna **Nota da revisão** você marca um comentário que não
gostou, mesmo depois de publicado: ele aprende com isso também.

## A lista de quem comentar

Dois jeitos, e dá para misturar:

- **O Claude monta.** Digite `/replai` e peça "monta a lista com: <nomes, empresas ou um tema>". Ele
  procura o LinkedIn e o X de cada pessoa, mostra uma tabela e só põe na lista com o seu ok. O que ele
  não achar com certeza fica em branco, nunca inventado.
- **Você preenche.** Peça ao `/replai` "me dá o modelo da lista": ele põe o arquivo em **Documentos >
  Replai** (abre no Excel, colunas Nome, LinkedIn, X, Prioridade, Incluir, Observação). Apague as linhas
  de exemplo, preencha e mande o arquivo para o `/replai`. Pode ser só LinkedIn ou só X: a coluna da outra rede fica vazia.

## Quantos comentários saem por dia

| | Padrão | Máximo que dá para pedir |
|---|---|---|
| LinkedIn | 20 comentários e 40 curtidas | 40 e 80 |
| X | 15 comentários e 30 curtidas | 30 e 60 |

Para mudar, peça "aumenta o teto do LinkedIn para 40" (ou um número menor). Acima do máximo o Replai não
vai, de propósito: é o que segura a conta longe de restrição.

Mesmo com o teto alto, sai menos nos primeiros dias e em alguns casos:

- **Aquecimento.** Nas duas primeiras semanas de uma conta (ou depois de refazer a conta) ele faz 40% do
  teto na 1ª semana e 70% na 2ª. Na 3ª, o teto inteiro.
- **Fim de semana:** metade. **Por hora:** no máximo 10 no LinkedIn e 8 no X. **Horário:** das 8h às
  22h (no X, até 23h).
- **Posts que não entram:** post velho (até 14 dias no LinkedIn e 48 h no X, com preferência para as
  primeiras 24 h no LinkedIn e 6 h no X), um post por pessoa por rodada, a mesma pessoa só uma vez a
  cada 7 dias no LinkedIn (3 no X), e no X as respostas a posts de outros.
- **O escritor pula** o post em que não tem nada útil a dizer. É normal metade dos candidatos ficar
  de fora.

**Para comentar mais e mais cedo:** uma rodada por dia de manhã nas duas redes e, depois das 3 rodadas
revisadas sem correção, o vigia, que responde de 5 a 25 minutos depois que alguém da lista posta.

**A voz de cada rede é separada.** No X ela costuma ser mais curta. Quando você corrige vários
comentários na revisão, o Replai propõe regras novas para a voz e só grava com o seu ok (em 18/11, no
X de uma conta de teste: uma frase só, afirmando em vez de perguntar).

## Combinados importantes

- **A conta roda num PC só.** Não instale o Replai da mesma conta em outro computador.
- **Seus dados ficam em Documentos > Replai.** Não apague nem troque essa pasta.
- **Versão nova:** quando sair, o `/replai` avisa e pergunta se pode atualizar. Responda ok, depois
  abra uma conversa nova e digite `/replai`. Os dados continuam.
- **Trocar de PC:** copie o zip mais recente de **Documentos > Replai > _copias** para o PC novo,
  instale o Replai lá e peça "restaura o Replai", arrastando o zip.
- **O vigia precisa do computador ligado e da sua sessão aberta** (pode bloquear a tela, só não
  desligue nem saia da conta).
- **Os limites são do Replai** (quantos comentários por dia, horário, pausas). Você escolhe o teto do
  dia até o máximo dele (veja "Quantos comentários saem por dia"), nunca acima.
- **Se ele disser que parou por verificação, captcha ou limite, pare por hoje.** Não tente à mão: no
  dia seguinte ele volta sozinho.
- **Ele nunca comenta duas vezes no mesmo post**, e nunca digita senha nem código: login é sempre você.
- **Respostas e mensagens que a conta receber** chegam na caixa dela, como sempre.

## Deu problema?

Digite `/replai` e conte o que aconteceu, com as suas palavras. Ele sabe o que fazer na maioria dos
casos e, quando não souber, diz o que mandar para quem mantém o Replai.
