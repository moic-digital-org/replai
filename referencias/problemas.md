# Problemas comuns

Primeiro passo para qualquer problema: `testar` (segundo plano). Ele aponta o item que falhou.

O robô trabalha no Chrome do Replai (uma pasta só dele, separada do Chrome de todo dia), numa área de
trabalho escondida do Windows (nenhuma janela pisca na tela). Para investigar, você (Claude) pode rodar
o comando com a variável `REPLAI_VISIVEL=1`: a janela volta a aparecer. No Mac, depois do login, o
Chrome do Replai abre escondido (como no Cmd+H) em tudo, rodada e vigia: uma janela, uma aba que as
redes revezam.

| O script diz | O que é | O que fazer |
|---|---|---|
| "não está logado nesta sessão" ou "a sessão caiu: rode o login" | a rede deslogou (a outra continua rodando). Até um login dar certo, o Replai não abre mais essa rede, nem no vigia: assim ele não fica abrindo e fechando abas | `login` (segundo plano; uma janela, uma aba por rede) e repita o pedido |
| código 3, "ocupado por outra rodada" | o navegador é um só (X, LinkedIn e campanha de DM) e outra rodada está com ele | esperar terminar; no vigia é normal de vez em quando (ele tenta na próxima). Se tiver certeza de que nada roda, apagar o arquivo que a mensagem indica |
| "RODADA PARADA", "CAPTCHA", "LIMIT" | o LinkedIn desconfiou | parar por hoje; não resolver captcha, não tentar à mão. A rede volta amanhã sozinha |
| não consegue entrar nas abas do login ("algo deu errado", "navegador pode não ser seguro") ou o fim diz "NÃO logado" | Replai de antes de 29/10 | instalar a versão nova e rodar `login` de novo. Nunca entrar pela janela do robô: o Google recusa |
| "o Chrome do Replai não abriu" | uma janela do Chrome do Replai ficou aberta de outro jeito (por exemplo, a do login) | fechar essa janela (no Mac, Cmd+Q nela) e repetir |
| depois de atualizar, ele pede a configuração de novo, ou a pasta Documentos > Replai sumiu | a pasta de dados foi trocada ou apagada (por exemplo, um zip novo descompactado por cima dela) | `copia` lista as cópias (o instalador faz uma antes de cada atualização) e `restaurar` põe de volta; depois só o `login`. Para atualizar, use sempre "instala o Replai" com o link do GitHub, nunca a pasta de dados |
| o post falhou ("outro elemento cobre o botão", "o botão apareceu mas não ficou pronto para o clique", "o elemento não apareceu na página", "nem editor nem botão") | a página do post não ficou como o robô esperava | o print de cada falha fica em `Documentos\Replai\<Conta>\rodada\<rede>\falhas\`: mande os prints e o motivo a quem mantém o Replai. Se repetir em todos os posts, `calibrar --rede linkedin` |
| o PC não tem Chrome | o Replai usa o Brave do PC (ou, sem nenhum dos dois, o navegador próprio dele) | nada: login e robô usam sempre o mesmo navegador. Instalar o Chrome depois pede `login` de novo |
| "teto pela metade" no status | duas paradas em 7 dias | nada: o Replai segura sozinho por uma semana |
| "o linkedin logado é '...', mas a conta é '...'" | o navegador está com outra conta | refazer o login com a conta certa |
| `testar`: "conta aprendida agora, confirme" | a configuração ficou sem o perfil da conta e ele aprendeu de quem está logado | perguntar a quem opera se é a conta certa; se não for, `conta --rede <rede> --perfil "<link certo>"` e `login` com a conta certa |
| "a página demorou demais para responder" | a rede ficou lenta ou a aba travou; a outra rede segue | nada se repetir pouco; se repetir em toda rodada, `testar` e mandar o resultado a quem mantém o Replai |
| "o comando travou e foi encerrado" | um comando passou de 3 h (página que não respondia) | `testar`; se o próximo comando disser "ocupado", esperar ou apagar o arquivo que a mensagem indica |
| "telas de post irreconhecíveis" | o LinkedIn mudou a página | `calibrar --rede linkedin` e mandar o resultado a quem mantém o Replai |
| "a conta ainda não tem voz" | falta a voz da rede | `referencias/voz.md`, "Criar" |
| "nenhum perfil nas listas ativas" | lista vazia ou pausada | `lista --rede <rede> --nome Principal --planilha "<link>"` |
| "fora do horário" / "teto de comentários do dia" | limite do dia ou da hora (no fuso do PC) | explicar e oferecer rodar mais tarde ou amanhã |
| `planilha_atualizada: false` | a planilha estava aberta no Excel | fechar o Excel e rodar `status` (nada se perde) |
| muitos `reprovados` seguidos pelo mesmo motivo | regra do validador dura demais ou escritor teimoso | mostrar os motivos a quem mantém o Replai |
| "incerto" no relatório | clicou e não conseguiu conferir | quem opera olha o post no LinkedIn; o Replai nunca repete esse post |
| a mesma conta roda em dois PCs | o registro é por PC: o volume do dia dobra | uma das instalações para (a outra continua com o histórico dela) |
| sininho: `sem_botao` ou `nao_confirmou` em quase todos | o LinkedIn mudou o botão de notificações do perfil | `calibrar --rede linkedin` e mandar o `sininho` do resultado a quem mantém o Replai (quem falhou tenta de novo no dia seguinte) |
| vigia do LinkedIn sempre com "nenhum aviso novo", mas a pessoa postou | o sininho dela ainda não foi ligado, ou a página de notificações mudou | `sininho`; se continuar, `calibrar --rede linkedin` (mostra `avisos_lidos`) e mandar a quem mantém o Replai |
| "BLOQUEIO" no X (`account/access`) | o X travou a conta e pede verificação | parar o vigia do X (`vigia --rede x --desligar`), a pessoa da conta resolve no X à mão; religar depois |
| vigia: "o Claude Code de linha de comando não está instalado" | falta o `claude` no PC | instalador do Replai e o passo "Claude Code" do `configurar.md` |
| vigia: "o Claude Code falhou: Not logged in" | o login do Claude Code expirou | `"<claude_code_caminho do checar>" auth login` (segundo plano) e autorizar no navegador |
| vigia: "You've hit your session limit" | o plano de quem opera bateu o limite | nada: o vigia tenta de novo nas próximas execuções; se repetir muito, desligar o vigia por hoje |
| o `ultimo_vigia` está velho (horas) | o computador dormiu, a sessão fechou ou o agendamento foi apagado | conferir o computador; `vigia --ligar` recria o agendamento (tarefa do Windows ou agente do launchd no Mac) |
| Mac: "o agendador do sistema recusou o vigia" | o launchd não aceitou o agente | `vigia --desligar` e `vigia --ligar`; se repetir, mandar a mensagem a quem mantém o Replai |
| `/replai` não aparece depois de instalar | o Claude só vê skill nova numa conversa nova | abrir uma conversa nova; se não aparecer, rodar `scripts/instalar.py` de novo e conferir `~/.claude/skills/replai/SKILL.md` |
| "a planilha do Google não está aberta para quem tem o link" | a planilha é restrita | compartilhar como "qualquer pessoa com o link pode ver" (ou baixar como .xlsx e usar `--excel`) |
| `coletar`: "perfil: LinkedIn respondeu 403" em uma ou duas pessoas | o perfil mudou de endereço, saiu do ar ou restringe quem vê | conferir o link na planilha; se repetir nos dias seguintes, tirar a pessoa da lista |
| X: "a caixa de resposta não apareceu (respostas restritas?)" | o autor deixou só quem ele segue ou menciona responder | nada: o post fica na fila e é pulado; se for sempre a mesma pessoa, tirar da lista do X |
