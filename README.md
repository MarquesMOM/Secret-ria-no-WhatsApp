# Secretária no WhatsApp

Bot de WhatsApp que gerencia o seu Google Agenda. Você escreve como numa conversa ("o que tenho amanhã?", "marca dentista sexta às 15h", "remarca a reunião para 16h", "cancela o almoço de quinta") e ela consulta, cria, remarca ou cancela os compromissos. Ela também manda um lembrete 30 minutos antes de cada compromisso e um resumo da agenda toda manhã.

## Como funciona

```
WhatsApp ──> Meta (Cloud API) ──> webhook /webhook (Cloud Run)
                                        │
                                        ├── Claude (entende o pedido e escolhe a ação)
                                        └── Google Calendar API (lê e altera a agenda)

Cloud Scheduler ──> /tasks/reminders (a cada 5 min) e /tasks/daily-summary (7h)
```

Só o número em `OWNER_PHONE` consegue conversar com ela. Mensagens de outros números são ignoradas.

## Passo a passo de configuração

### 1. Claude (chave da API)
1. Crie uma conta em https://console.anthropic.com e adicione créditos (US$ 5 duram bastante).
2. Em **API Keys**, gere uma chave e guarde como `ANTHROPIC_API_KEY`.

### 2. Google Agenda
1. Em https://console.cloud.google.com crie um projeto (ex.: `secretaria`).
2. Em **APIs e serviços > Biblioteca**, ative a **Google Calendar API**.
3. Em **Tela de consentimento OAuth**, escolha **Externo**, preencha o nome do app e adicione o seu e-mail como **usuário de teste**. Depois clique em **Publicar app** (assim o acesso não expira em 7 dias; como é só para você, não precisa de verificação).
4. Em **Credenciais > Criar credenciais > ID do cliente OAuth**, escolha **App para computador** e baixe o JSON.
5. No seu computador, rode:
   ```
   pip install google-auth-oauthlib
   python scripts/obter_token_google.py client_secret_XXXX.json
   ```
   Faça login com a conta da agenda e copie as três linhas impressas para o `.env`.

### 3. WhatsApp Cloud API (Meta)
1. Tenha um número só para a secretária (um chip pré-pago serve). Ele não pode estar em uso no app do WhatsApp; se estiver, apague a conta do WhatsApp nesse número antes.
2. Em https://developers.facebook.com crie um app do tipo **Empresa** e adicione o produto **WhatsApp**.
3. Em **WhatsApp > Configuração da API**, adicione e verifique o seu número da secretária. Anote o **ID do número de telefone** (`WHATSAPP_PHONE_NUMBER_ID`).
4. Gere um token permanente: em https://business.facebook.com > **Configurações > Usuários do sistema**, crie um usuário de sistema administrador, atribua o app e gere um token com as permissões `whatsapp_business_messaging` e `whatsapp_business_management` (`WHATSAPP_TOKEN`).
5. Em **Configurações do app > Básico**, copie a **Chave secreta do app** (`WHATSAPP_APP_SECRET`).
6. Crie o template de mensagem (necessário para lembretes quando você não conversou com ela nas últimas 24h): em **WhatsApp Manager > Modelos de mensagem**, crie:
   - Nome: `aviso_secretaria`, categoria **Utilidade**, idioma **Português (BR)**
   - Corpo: `Olá! Aviso da sua secretária: {{1}} ({{2}}). Responda esta mensagem para ver os detalhes.`
7. Cadastre uma forma de pagamento na conta do WhatsApp Business (cobra só os templates enviados, centavos cada).
8. O webhook é configurado depois do deploy (passo 5).

### 4. Deploy no Google Cloud Run
Com o [gcloud](https://cloud.google.com/sdk/docs/install) instalado e o `.env` preenchido (copie de `.env.example`):

```
gcloud config set project SEU_PROJETO
gcloud services enable run.googleapis.com cloudscheduler.googleapis.com cloudbuild.googleapis.com

# Converte o .env para o formato do Cloud Run e publica
grep -v '^#' .env | grep '=' | sed 's/=\(.*\)/: "\1"/' > env.yaml
gcloud run deploy secretaria --source . --region southamerica-east1 \
  --allow-unauthenticated --env-vars-file env.yaml --max-instances 1
rm env.yaml
```

O comando mostra a URL do serviço (algo como `https://secretaria-xxxx.a.run.app`). `--max-instances 1` mantém o histórico da conversa num lugar só.

### 5. Ligar o webhook
Em **WhatsApp > Configuração** no app da Meta:
- URL de callback: `https://SUA-URL/webhook`
- Token de verificação: o mesmo valor de `WHATSAPP_VERIFY_TOKEN`
- Clique em **Verificar e salvar** e assine o campo **messages**.

### 6. Lembretes e resumo diário
```
URL=https://SUA-URL
SEGREDO=valor_do_TASKS_SECRET
gcloud scheduler jobs create http secretaria-lembretes --location southamerica-east1 \
  --schedule "*/5 * * * *" --time-zone America/Sao_Paulo --http-method POST \
  --uri "$URL/tasks/reminders" --headers "x-tasks-secret=$SEGREDO"
gcloud scheduler jobs create http secretaria-resumo --location southamerica-east1 \
  --schedule "0 7 * * *" --time-zone America/Sao_Paulo --http-method POST \
  --uri "$URL/tasks/daily-summary" --headers "x-tasks-secret=$SEGREDO"
```

Pronto: mande "oi" do seu WhatsApp pessoal para o número da secretária.

## Custos esperados
- Cloud Run e Cloud Scheduler: dentro da cota gratuita para uso pessoal (o Scheduler dá 3 jobs grátis).
- Claude Haiku: poucos reais por mês com uso diário normal.
- WhatsApp: conversas que você inicia são grátis; templates de utilidade fora da janela de 24h custam centavos cada.

## Rodar localmente
```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt pytest
pytest
set -a; source .env; set +a
uvicorn app.main:app --reload --port 8080
```
Para a Meta alcançar sua máquina, exponha a porta com `ngrok http 8080` e use essa URL no webhook.

## Limitações atuais
- Entende só mensagens de texto (áudio fica para uma próxima versão).
- O histórico da conversa fica na memória e é perdido quando o servidor reinicia ou fica ocioso; a agenda em si nunca é afetada.
