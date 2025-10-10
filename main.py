import streamlit as st
import io
import google.generativeai as genai
from PIL import Image
import requests
import datetime
import os
from pymongo import MongoClient
from bson import ObjectId
import json
import hashlib
from google.genai import types

# Configuração inicial
st.set_page_config(
    layout="wide",
    page_title="Agente Generativo",
    page_icon="🤖"
)

# --- Sistema de Autenticação ---
def make_hashes(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    return make_hashes(password) == hashed_text

# Dados de usuário (em produção, isso deve vir de um banco de dados seguro)
users = {
    "admin": make_hashes("senha1234"),  # admin/senha1234
    "user1": make_hashes("password1"),  # user1/password1
    "user2": make_hashes("password2")   # user2/password2
}

def login():
    """Formulário de login"""
    st.title("🔒 Agente Generativo - Login")
    
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        submit_button = st.form_submit_button("Login")
        
        if submit_button:
            if username in users and check_hashes(password, users[username]):
                st.session_state.logged_in = True
                st.session_state.user = username
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos")

# Verificar se o usuário está logado
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    login()
    st.stop()

# --- CONEXÃO MONGODB (após login) ---
client = MongoClient("mongodb+srv://gustavoromao3345:RqWFPNOJQfInAW1N@cluster0.5iilj.mongodb.net/auto_doc?retryWrites=true&w=majority&ssl=true&ssl_cert_reqs=CERT_NONE&tlsAllowInvalidCertificates=true")
db = client['agentes_personalizados']
collection_agentes = db['agentes']
collection_conversas = db['conversas']

# Configuração da API do Gemini
gemini_api_key = os.getenv("GEM_API_KEY")
if not gemini_api_key:
    st.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    st.stop()

genai.configure(api_key=gemini_api_key)
modelo_vision = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.1})
modelo_texto = genai.GenerativeModel("gemini-2.5-flash")

# Configuração da API do Perplexity
perp_api_key = os.getenv("PERP_API_KEY")
if not perp_api_key:
    st.error("PERP_API_KEY não encontrada nas variáveis de ambiente")

# --- Configuração de Autenticação de Administrador ---
def check_admin_password():
    """Retorna True se o usuário fornecer a senha de admin correta."""
    
    def admin_password_entered():
        """Verifica se a senha de admin está correta."""
        if st.session_state["admin_password"] == "senha123":
            st.session_state["admin_password_correct"] = True
            st.session_state["admin_user"] = "admin"
            del st.session_state["admin_password"]
        else:
            st.session_state["admin_password_correct"] = False

    if "admin_password_correct" not in st.session_state:
        # Mostra o input para senha de admin
        st.text_input(
            "Senha de Administrador", 
            type="password", 
            on_change=admin_password_entered, 
            key="admin_password"
        )
        return False
    elif not st.session_state["admin_password_correct"]:
        # Senha incorreta, mostra input + erro
        st.text_input(
            "Senha de Administrador", 
            type="password", 
            on_change=admin_password_entered, 
            key="admin_password"
        )
        st.error("😕 Senha de administrador incorreta")
        return False
    else:
        # Senha correta
        return True

# --- Funções CRUD para Agentes ---
def criar_agente(nome, system_prompt, base_conhecimento, comments, planejamento, categoria, agente_mae_id=None, herdar_elementos=None):
    """Cria um novo agente no MongoDB"""
    agente = {
        "nome": nome,
        "system_prompt": system_prompt,
        "base_conhecimento": base_conhecimento,
        "comments": comments,
        "planejamento": planejamento,
        "categoria": categoria,
        "agente_mae_id": agente_mae_id,
        "herdar_elementos": herdar_elementos or [],
        "data_criacao": datetime.datetime.now(),
        "ativo": True
    }
    result = collection_agentes.insert_one(agente)
    return result.inserted_id

def listar_agentes():
    """Retorna todos os agentes ativos"""
    return list(collection_agentes.find({"ativo": True}).sort("data_criacao", -1))

def listar_agentes_para_heranca(agente_atual_id=None):
    """Retorna todos os agentes ativos que podem ser usados como mãe"""
    query = {"ativo": True}
    if agente_atual_id:
        # Excluir o próprio agente da lista de opções para evitar auto-herança
        if isinstance(agente_atual_id, str):
            agente_atual_id = ObjectId(agente_atual_id)
        query["_id"] = {"$ne": agente_atual_id}
    return list(collection_agentes.find(query).sort("data_criacao", -1))

def obter_agente(agente_id):
    """Obtém um agente específico pelo ID"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.find_one({"_id": agente_id})

def atualizar_agente(agente_id, nome, system_prompt, base_conhecimento, comments, planejamento, categoria, agente_mae_id=None, herdar_elementos=None):
    """Atualiza um agente existente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.update_one(
        {"_id": agente_id},
        {
            "$set": {
                "nome": nome,
                "system_prompt": system_prompt,
                "base_conhecimento": base_conhecimento,
                "comments": comments,
                "planejamento": planejamento,
                "categoria": categoria,
                "agente_mae_id": agente_mae_id,
                "herdar_elementos": herdar_elementos or [],
                "data_atualizacao": datetime.datetime.now()
            }
        }
    )

def desativar_agente(agente_id):
    """Desativa um agente (soft delete)"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.update_one(
        {"_id": agente_id},
        {"$set": {"ativo": False, "data_desativacao": datetime.datetime.now()}}
    )

def obter_agente_com_heranca(agente_id):
    """Obtém um agente com os elementos herdados aplicados"""
    agente = obter_agente(agente_id)
    if not agente or not agente.get('agente_mae_id'):
        return agente
    
    agente_mae = obter_agente(agente['agente_mae_id'])
    if not agente_mae:
        return agente
    
    elementos_herdar = agente.get('herdar_elementos', [])
    agente_completo = agente.copy()
    
    for elemento in elementos_herdar:
        if elemento == 'system_prompt' and not agente_completo.get('system_prompt'):
            agente_completo['system_prompt'] = agente_mae.get('system_prompt', '')
        elif elemento == 'base_conhecimento' and not agente_completo.get('base_conhecimento'):
            agente_completo['base_conhecimento'] = agente_mae.get('base_conhecimento', '')
        elif elemento == 'comments' and not agente_completo.get('comments'):
            agente_completo['comments'] = agente_mae.get('comments', '')
        elif elemento == 'planejamento' and not agente_completo.get('planejamento'):
            agente_completo['planejamento'] = agente_mae.get('planejamento', '')
    
    return agente_completo

def salvar_conversa(agente_id, mensagens, segmentos_utilizados=None):
    """Salva uma conversa no histórico"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    conversa = {
        "agente_id": agente_id,
        "mensagens": mensagens,
        "segmentos_utilizados": segmentos_utilizados,
        "data_criacao": datetime.datetime.now()
    }
    return collection_conversas.insert_one(conversa)

def obter_conversas(agente_id, limite=10):
    """Obtém o histórico de conversas de um agente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return list(collection_conversas.find(
        {"agente_id": agente_id}
    ).sort("data_criacao", -1).limit(limite))

# --- Função para construir contexto com segmentos selecionados ---
def construir_contexto(agente, segmentos_selecionados, historico_mensagens=None):
    """Constrói o contexto com base nos segmentos selecionados"""
    contexto = ""
    
    if "system_prompt" in segmentos_selecionados and agente.get('system_prompt'):
        contexto += f"### INSTRUÇÕES DO SISTEMA ###\n{agente['system_prompt']}\n\n"
    
    if "base_conhecimento" in segmentos_selecionados and agente.get('base_conhecimento'):
        contexto += f"### BASE DE CONHECIMENTO ###\n{agente['base_conhecimento']}\n\n"
    
    if "comments" in segmentos_selecionados and agente.get('comments'):
        contexto += f"### COMENTÁRIOS DO CLIENTE ###\n{agente['comments']}\n\n"
    
    if "planejamento" in segmentos_selecionados and agente.get('planejamento'):
        contexto += f"### PLANEJAMENTO ###\n{agente['planejamento']}\n\n"
    
    # Adicionar histórico se fornecido
    if historico_mensagens:
        contexto += "### HISTÓRICO DA CONVERSA ###\n"
        for msg in historico_mensagens:
            contexto += f"{msg['role']}: {msg['content']}\n"
        contexto += "\n"
    
    contexto += "### RESPOSTA ATUAL ###\nassistant:"
    
    return contexto

# --- Funções para processamento de vídeo ---
def processar_video_upload(video_file, segmentos_selecionados, agente, tipo_analise="completa"):
    """Processa vídeo upload e retorna análise"""
    try:
        # Ler bytes do vídeo
        video_bytes = video_file.read()
        
        # Construir contexto com segmentos selecionados
        contexto = construir_contexto(agente, segmentos_selecionados)
        
        # Definir prompt baseado no tipo de análise
        if tipo_analise == "completa":
            prompt = f"""
            {contexto}
            
            Analise este vídeo considerando as diretrizes fornecidas e forneça um relatório detalhado:
            
            ## 🎬 ANÁLISE DO VÍDEO
            
            ### 📊 Resumo Executivo
            [Forneça uma visão geral da conformidade do vídeo com as diretrizes]
            
            ### ✅ Pontos de Conformidade
            - [Liste os aspectos que estão em conformidade]
            
            ### ⚠️ Pontos de Atenção
            - [Liste os aspectos que precisam de ajustes]
            
            ### 🎯 Análise de Conteúdo
            - **Mensagem**: [Avalie se a mensagem está alinhada]
            - **Tom e Linguagem**: [Avalie o tom utilizado]
            - **Valores da Marca**: [Verifique alinhamento com valores]
            
            ### 🎨 Análise Visual
            - **Identidade Visual**: [Cores, logos, tipografia]
            - **Qualidade Técnica**: [Iluminação, enquadramento, áudio]
            - **Consistência**: [Manutenção da identidade ao longo do vídeo]
            
            ### 🔊 Análise de Áudio
            - [Qualidade, trilha sonora, voz]
            
            ### 📋 Recomendações Específicas
            [Liste recomendações práticas para melhorias]
            
            ### 🏆 Avaliação Final
            [Aprovado/Reprovado/Com ajustes] - [Justificativa]
            """
        elif tipo_analise == "rapida":
            prompt = f"""
            {contexto}
            
            Faça uma análise rápida deste vídeo focando nos aspectos mais críticos:
            
            ### 🔍 Análise Rápida
            - **Conformidade Geral**: [Avaliação geral]
            - **Principais Pontos Positivos**: [2-3 pontos]
            - **Principais Problemas**: [2-3 pontos críticos]
            - **Recomendação Imediata**: [Aprovar/Reprovar/Ajustar]
            """
        else:  # análise técnica
            prompt = f"""
            {contexto}
            
            Faça uma análise técnica detalhada do vídeo:
            
            ### 🛠️ Análise Técnica
            - **Qualidade de Vídeo**: [Resolução, estabilidade, compression]
            - **Qualidade de Áudio**: [Clareza, ruído, mixagem]
            - **Edição e Transições**: [Fluidez, ritmo, cortes]
            - **Aspectos Técnicos Conformes**: 
            - **Problemas Técnicos Identificados**:
            - **Recomendações Técnicas**:
            """
        
        # Processar vídeo com a API Gemini
        response = modelo_vision.generate_content(
            contents=[
                types.Part(
                    inline_data=types.Blob(
                        data=video_bytes,
                        mime_type=video_file.type
                    )
                ),
                types.Part(text=prompt)
            ]
        )
        
        return response.text
        
    except Exception as e:
        return f"Erro ao processar vídeo: {str(e)}"

def processar_url_youtube(youtube_url, segmentos_selecionados, agente, tipo_analise="completa"):
    """Processa URL do YouTube e retorna análise"""
    try:
        # Construir contexto com segmentos selecionados
        contexto = construir_contexto(agente, segmentos_selecionados)
        
        # Definir prompt baseado no tipo de análise
        if tipo_analise == "completa":
            prompt = f"""
            {contexto}
            
            Analise este vídeo do YouTube considerando as diretrizes fornecidas:
            
            ## 🎬 ANÁLISE DO VÍDEO - YOUTUBE
            
            ### 📊 Resumo Executivo
            [Avaliação geral de conformidade]
            
            ### 🎯 Conteúdo e Mensagem
            - Alinhamento com diretrizes: 
            - Clareza da mensagem:
            - Tom e abordagem:
            
            ### 🎨 Aspectos Visuais
            - Identidade visual:
            - Qualidade de produção:
            - Consistência da marca:
            
            ### 🔊 Aspectos de Áudio
            - Qualidade do áudio:
            - Trilha sonora:
            - Narração/diálogo:
            
            ### 📈 Estrutura e Engajamento
            - Ritmo do vídeo:
            - Manutenção do interesse:
            - Chamadas para ação:
            
            ### ✅ Pontos Fortes
            - [Liste os pontos positivos]
            
            ### ⚠️ Pontos de Melhoria
            - [Liste sugestões de melhoria]
            
            ### 🏆 Recomendação Final
            [Status e justificativa]
            """
        
        # Processar URL do YouTube
        response = modelo_vision.generate_content(
            contents=[
                types.Part(
                    file_data=types.FileData(file_uri=youtube_url)
                ),
                types.Part(text=prompt)
            ]
        )
        
        return response.text
        
    except Exception as e:
        return f"Erro ao processar URL do YouTube: {str(e)}"

# --- Funções para busca web com Perplexity ---
def buscar_perplexity(pergunta, contexto_agente=None, focus=None, urls_especificas=None):
    """Faz busca na web usando a API do Perplexity"""
    try:
        if not perp_api_key:
            return "❌ Erro: Chave da API Perplexity não configurada"
        
        # Construir o prompt com contexto do agente se fornecido
        prompt_final = pergunta
        if contexto_agente:
            prompt_final = f"""
            Contexto do agente:
            {contexto_agente}
            
            Pergunta: {pergunta}
            
            Por favor, responda considerando o contexto acima e complemente com informações atualizadas da web.
            """
        
        # Configurar os parâmetros da requisição
        url = "https://api.perplexity.ai/chat/completions"
        
        headers = {
            "Authorization": perp_api_key,
            "Content-Type": "application/json"
        }
        
        # Configurar o payload
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "Seja preciso e forneça informações atualizadas. Cite fontes quando relevante."
                },
                {
                    "role": "user",
                    "content": prompt_final
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.1,
            "top_p": 0.9,
            "return_citations": True,
            "search_domain_filters": urls_especificas if urls_especificas else None
        }
        
        # Fazer a requisição
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            resposta = data['choices'][0]['message']['content']
            
            # Adicionar citações se disponíveis
            if 'citations' in data and data['citations']:
                resposta += "\n\n### 🔍 Fontes Consultadas:\n"
                for i, citation in enumerate(data['citations'], 1):
                    resposta += f"{i}. {citation}\n"
            
            return resposta
        else:
            return f"❌ Erro na API Perplexity: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"❌ Erro ao fazer busca: {str(e)}"

def analisar_urls_perplexity(urls, pergunta, contexto_agente=None):
    """Analisa URLs específicas usando Perplexity"""
    try:
        if not perp_api_key:
            return "❌ Erro: Chave da API Perplexity não configurada"
        
        # Construir prompt para análise de URLs
        prompt = f"""
        Analise as seguintes URLs e responda à pergunta com base no conteúdo delas:
        
        URLs para análise:
        {chr(10).join([f'- {url}' for url in urls])}
        
        Pergunta: {pergunta}
        """
        
        if contexto_agente:
            prompt = f"""
            Contexto do agente:
            {contexto_agente}
            
            {prompt}
            
            Por favor, responda considerando o contexto do agente e as informações das URLs fornecidas.
            """
        
        url = "https://api.perplexity.ai/chat/completions"
        
        headers = {
            "Authorization": perp_api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "sonar",
            "messages": [
                {
                    "role": "system",
                    "content": "Analise o conteúdo das URLs fornecidas e responda com base nelas. Cite trechos específicos quando relevante."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": 2000,
            "temperature": 0.1,
            "top_p": 0.9,
            "return_citations": True,
            "search_domain_filters": urls
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            resposta = data['choices'][0]['message']['content']
            
            if 'citations' in data and data['citations']:
                resposta += "\n\n### 🔍 URLs Analisadas:\n"
                for i, citation in enumerate(data['citations'], 1):
                    resposta += f"{i}. {citation}\n"
            
            return resposta
        else:
            return f"❌ Erro na API Perplexity: {response.status_code} - {response.text}"
            
    except Exception as e:
        return f"❌ Erro ao analisar URLs: {str(e)}"

# --- Função para Otimização SEO ---
def gerar_analise_seo(conteudo, agente, palavra_chave_principal=None, tipo_conteudo="blog"):
    """Gera análise completa de SEO para o conteúdo fornecido"""
    
    # Construir contexto com segmentos do agente
    contexto = construir_contexto(agente, ["system_prompt", "base_conhecimento", "planejamento"])
    
    # Definir prompt específico para SEO
    prompt = f"""
    {contexto}
    
    ## 🎯 ANÁLISE DE OTIMIZAÇÃO SEO
    
    Analise o seguinte conteúdo para otimização SEO e forneça um relatório detalhado:
    
    **Informações do Conteúdo:**
    - Tipo: {tipo_conteudo}
    {f"- Palavra-chave Principal: {palavra_chave_principal}" if palavra_chave_principal else "- Palavra-chave: A ser identificada"}
    
    **Conteúdo para Análise:**
    {conteudo}
    
    ### 📊 RESUMO EXECUTIVO
    [Avaliação geral do conteúdo em termos de SEO]
    
    ### 🔍 ANÁLISE DE PALAVRAS-CHAVE
    **Palavras-chave Identificadas:**
    - Principal: [identificar/sugerir]
    - Secundárias: [listar 3-5]
    - LSI (Latent Semantic Indexing): [sugerir 3-5]
    
    **Densidade e Uso:**
    - Frequência da palavra-chave principal: 
    - Distribuição ao longo do texto:
    - Sugestões de otimização:
    
    ### 📝 ANÁLISE DE CONTEÚDO
    **Meta Informações:**
    - **Título SEO** (atual/sugerido): 
      [Avaliar e sugerir título otimizado (50-60 caracteres)]
    
    - **Meta Description** (atual/sugerida):
      [Avaliar e sugerir descrição otimizada (120-158 caracteres)]
    
    **Estrutura do Conteúdo:**
    - Títulos H1, H2, H3: [Avaliar hierarquia e uso de palavras-chave]
    - Comprimento do conteúdo: [Avaliar se é adequado para o tópico]
    - Legibilidade: [Avaliar clareza e facilidade de leitura]
    - Valor para o usuário: [Avaliar qualidade e profundidade]
    
    ### 🔗 OTIMIZAÇÃO ON-PAGE
    **Elementos Técnicos:**
    - URLs: [Sugerir estrutura otimizada]
    - Imagens: [Sugerir otimização de alt text e nomes de arquivo]
    - Links Internos: [Sugerir oportunidades]
    - Links Externos: [Sugerir fontes autoritativas]
    
    **Engajamento:**
    - Chamadas para ação (CTAs): [Avaliar e sugerir]
    - Elementos visuais: [Sugerir melhorias]
    - Interatividade: [Sugerir elementos engajadores]
    
    ### 📈 OTIMIZAÇÃO OFF-PAGE
    **Estratégias de Link Building:**
    - [Sugerir 3-5 estratégias específicas]
    
    **Compartilhamento Social:**
    - Títulos para redes sociais: [Sugerir variações]
    - Descrições otimizadas: [Para Facebook, Twitter, LinkedIn]
    
    ### 🎯 SCORE SEO
    **Pontuação por Categoria:**
    - Palavras-chave: [0-10]
    - Conteúdo: [0-10] 
    - Técnico: [0-10]
    - Experiência do Usuário: [0-10]
    
    **Pontuação Total:** [0-40]
    
    ### 🚀 AÇÕES RECOMENDADAS
    **Prioridade Alta:**
    - [Listar 3-5 ações críticas]
    
    **Prioridade Média:**
    - [Listar 3-5 ações importantes]
    
    **Prioridade Baixa:**
    - [Listar 2-3 otimizações adicionais]
    
    ### 💡 CONTEÚDO SUGERIDO
    **Tópicos Relacionados:**
    - [Sugerir 3-5 tópicos para pillar content]
    
    **Perguntas Frequentes:**
    - [Listar 3-5 perguntas que o conteúdo responde]
    
    ### 📋 CHECKLIST DE OTIMIZAÇÃO
    - [ ] Título otimizado com palavra-chave
    - [ ] Meta description atrativa
    - [ ] Estrutura de headings adequada
    - [ ] Conteúdo de valor e profundidade
    - [ ] Palavras-chave bem distribuídas
    - [ ] Imagens otimizadas
    - [ ] Links internos relevantes
    - [ ] CTAs eficazes
    - [ ] Conteúdo mobile-friendly
    - [ ] Velocidade de carregamento adequada
    """
    
    try:
        pre_resposta = modelo_texto.generate_content(prompt)
        resposta = modelo_texto.generate_content(f'''Com base no, utilize como referência a análise de otimização de SEO e gere o conteúdo otimizado por INTEIRO
            ###BEGIN CONTEUDO ORIGINAL A SER AJUSTADO###
            {conteudo}
            ###END CONTEUDO ORIGINAL A SER AJUSTADO###
            
            ###BEGIN ANALISE DE PONTOS DE MELHORIA###
            {pre_resposta}
            ###END ANALISE DE PONTOS DE MELHORIA###

            
            ''')
        
        return resposta.text
    except Exception as e:
        return f"❌ Erro ao gerar análise SEO: {str(e)}"

# --- Função para Revisão Ortográfica ---
def revisar_texto_ortografia(texto, agente, segmentos_selecionados):
    """Faz revisão ortográfica e gramatical considerando as bases do agente"""
    
    # Construir contexto com segmentos selecionados
    contexto = construir_contexto(agente, segmentos_selecionados)
    
    prompt = f"""
    {contexto}
    
    ## 📝 REVISÃO ORTOGRÁFICA E GRAMATICAL
    
    Faça uma revisão completa do texto abaixo, considerando as diretrizes fornecidas:
    
    ### TEXTO ORIGINAL:
    {texto}
    
    ### FORMATO DA RESPOSTA:
    
    ## 📊 RESUMO DA REVISÃO
    [Resumo geral dos problemas encontrados e qualidade do texto]
    
    ## ✅ PONTOS FORTES
    - [Listar aspectos positivos do texto]
    
    ## ⚠️ PROBLEMAS IDENTIFICADOS
    
    ### 🔤 Ortografia
    - [Listar erros ortográficos encontrados]
    
    ### 📖 Gramática
    - [Listar erros gramaticais]
    
    ### 🔠 Pontuação
    - [Listar problemas de pontuação]
    
    ### 📝 Estilo e Clareza
    - [Sugestões para melhorar clareza e estilo]
    
    ### 🎯 Adequação às Diretrizes
    - [Avaliação de conformidade com as diretrizes fornecidas]
    
    ## 📋 TEXTO REVISADO
    [Apresentar o texto completo com as correções aplicadas]
    
    ## 🔍 EXPLICAÇÃO DAS PRINCIPAIS ALTERAÇÕES
    [Explicar as mudanças mais importantes realizadas]
    
    ## 📈 SCORE DE QUALIDADE
    **Ortografia:** [0-10]
    **Gramática:** [0-10]
    **Clareza:** [0-10]
    **Conformidade:** [0-10]
    **Total:** [0-40]
    """
    
    try:
        resposta = modelo_texto.generate_content(prompt)
        return resposta.text
    except Exception as e:
        return f"❌ Erro ao realizar revisão: {str(e)}"

# --- Interface Principal ---
st.sidebar.title(f"🤖 Bem-vindo, {st.session_state.user}!")

# Botão de logout na sidebar
if st.sidebar.button("🚪 Sair", key="logout_btn"):
    for key in ["logged_in", "user", "admin_password_correct", "admin_user"]:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

st.title("🤖 Agente Generativo Personalizável")

# Inicializar estado da sessão
if "agente_selecionado" not in st.session_state:
    st.session_state.agente_selecionado = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "segmentos_selecionados" not in st.session_state:
    st.session_state.segmentos_selecionados = ["system_prompt", "base_conhecimento", "comments", "planejamento"]

# Menu de abas - ADICIONANDO A NOVA ABA DE REVISÃO ORTOGRÁFICA
tab_chat, tab_gerenciamento, tab_aprovacao, tab_video, tab_geracao, tab_resumo, tab_busca, tab_seo, tab_revisao = st.tabs([
    "💬 Chat", 
    "⚙️ Gerenciar Agentes", 
    "✅ Validação", 
    "🎬 Validação de Vídeo",
    "✨ Geração de Conteúdo",
    "📝 Resumo de Textos",
    "🌐 Busca Web",
    "🚀 Otimização SEO",
    "📝 Revisão Ortográfica"  # NOVA ABA
])

with tab_gerenciamento:
    st.header("Gerenciamento de Agentes")
    
    # Verificar autenticação apenas para gerenciamento
    if st.session_state.user != "admin":
        st.warning("Acesso restrito a administradores")
    else:
        # Verificar senha de admin
        if not check_admin_password():
            st.warning("Digite a senha de administrador")
        else:
            # Mostra o botão de logout admin
            if st.button("Logout Admin", key="admin_logout"):
                if "admin_password_correct" in st.session_state:
                    del st.session_state["admin_password_correct"]
                if "admin_user" in st.session_state:
                    del st.session_state["admin_user"]
                st.rerun()
            
            st.write(f'Bem-vindo administrador!')
            
            # Subabas para gerenciamento
            sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Criar Agente", "Editar Agente", "Gerenciar Agentes"])
            
            with sub_tab1:
                st.subheader("Criar Novo Agente")
                
                with st.form("form_criar_agente"):
                    nome_agente = st.text_input("Nome do Agente:")
                    
                    # Seleção de categoria
                    categoria = st.selectbox(
                        "Categoria:",
                        ["Social", "SEO", "Conteúdo"],
                        help="Organize o agente por área de atuação"
                    )
                    
                    # Opção para criar como agente filho
                    criar_como_filho = st.checkbox("Criar como agente filho (herdar elementos)")
                    
                    agente_mae_id = None
                    herdar_elementos = []
                    
                    if criar_como_filho:
                        # Listar TODOS os agentes disponíveis para herança
                        agentes_mae = listar_agentes_para_heranca()
                        if agentes_mae:
                            agente_mae_options = {f"{agente['nome']} ({agente.get('categoria', 'Social')})": agente['_id'] for agente in agentes_mae}
                            agente_mae_selecionado = st.selectbox(
                                "Agente Mãe:",
                                list(agente_mae_options.keys()),
                                help="Selecione o agente do qual este agente irá herdar elementos"
                            )
                            agente_mae_id = agente_mae_options[agente_mae_selecionado]
                            
                            st.subheader("Elementos para Herdar")
                            herdar_elementos = st.multiselect(
                                "Selecione os elementos a herdar do agente mãe:",
                                ["system_prompt", "base_conhecimento", "comments", "planejamento"],
                                help="Estes elementos serão herdados do agente mãe se não preenchidos abaixo"
                            )
                        else:
                            st.info("Nenhum agente disponível para herança. Crie primeiro um agente mãe.")
                    
                    system_prompt = st.text_area("Prompt de Sistema:", height=150, 
                                                placeholder="Ex: Você é um assistente especializado em...",
                                                help="Deixe vazio se for herdar do agente mãe")
                    base_conhecimento = st.text_area("Brand Guidelines:", height=200,
                                                   placeholder="Cole aqui informações, diretrizes, dados...",
                                                   help="Deixe vazio se for herdar do agente mãe")
                    comments = st.text_area("Comentários do cliente:", height=200,
                                                   placeholder="Cole aqui os comentários de ajuste do cliente (Se houver)",
                                                   help="Deixe vazio se for herdar do agente mãe")
                    planejamento = st.text_area("Planejamento:", height=200,
                                               placeholder="Estratégias, planejamentos, cronogramas...",
                                               help="Deixe vazio se for herdar do agente mãe")
                    
                    submitted = st.form_submit_button("Criar Agente")
                    if submitted:
                        if nome_agente:
                            agente_id = criar_agente(
                                nome_agente, 
                                system_prompt, 
                                base_conhecimento, 
                                comments, 
                                planejamento,
                                categoria,
                                agente_mae_id if criar_como_filho else None,
                                herdar_elementos if criar_como_filho else []
                            )
                            st.success(f"Agente '{nome_agente}' criado com sucesso na categoria {categoria}!")
                        else:
                            st.error("Nome é obrigatório!")
            
            with sub_tab2:
                st.subheader("Editar Agente Existente")
                
                agentes = listar_agentes()
                if agentes:
                    agente_options = {agente['nome']: agente for agente in agentes}
                    agente_selecionado_nome = st.selectbox("Selecione o agente para editar:", 
                                                         list(agente_options.keys()))
                    
                    if agente_selecionado_nome:
                        agente = agente_options[agente_selecionado_nome]
                        
                        with st.form("form_editar_agente"):
                            novo_nome = st.text_input("Nome do Agente:", value=agente['nome'])
                            
                            # Categoria
                            nova_categoria = st.selectbox(
                                "Categoria:",
                                ["Social", "SEO", "Conteúdo"],
                                index=["Social", "SEO", "Conteúdo"].index(agente.get('categoria', 'Social')),
                                help="Organize o agente por área de atuação"
                            )
                            
                            # Informações de herança
                            if agente.get('agente_mae_id'):
                                agente_mae = obter_agente(agente['agente_mae_id'])
                                if agente_mae:
                                    st.info(f"🔗 Este agente é filho de: {agente_mae['nome']}")
                                    st.write(f"Elementos herdados: {', '.join(agente.get('herdar_elementos', []))}")
                            
                            # Opção para tornar independente
                            if agente.get('agente_mae_id'):
                                tornar_independente = st.checkbox("Tornar agente independente (remover herança)")
                                if tornar_independente:
                                    agente_mae_id = None
                                    herdar_elementos = []
                                else:
                                    agente_mae_id = agente.get('agente_mae_id')
                                    herdar_elementos = agente.get('herdar_elementos', [])
                            else:
                                agente_mae_id = None
                                herdar_elementos = []
                                # Opção para adicionar herança
                                adicionar_heranca = st.checkbox("Adicionar herança de agente mãe")
                                if adicionar_heranca:
                                    # Listar TODOS os agentes disponíveis para herança (excluindo o próprio)
                                    agentes_mae = listar_agentes_para_heranca(agente['_id'])
                                    if agentes_mae:
                                        agente_mae_options = {f"{agente_mae['nome']} ({agente_mae.get('categoria', 'Social')})": agente_mae['_id'] for agente_mae in agentes_mae}
                                        if agente_mae_options:
                                            agente_mae_selecionado = st.selectbox(
                                                "Agente Mãe:",
                                                list(agente_mae_options.keys()),
                                                help="Selecione o agente do qual este agente irá herdar elementos"
                                            )
                                            agente_mae_id = agente_mae_options[agente_mae_selecionado]
                                            herdar_elementos = st.multiselect(
                                                "Elementos para herdar:",
                                                ["system_prompt", "base_conhecimento", "comments", "planejamento"],
                                                default=herdar_elementos
                                            )
                                        else:
                                            st.info("Nenhum agente disponível para herança.")
                                    else:
                                        st.info("Nenhum agente disponível para herança.")
                            
                            novo_prompt = st.text_area("Prompt de Sistema:", value=agente['system_prompt'], height=150)
                            nova_base = st.text_area("Brand Guidelines:", value=agente.get('base_conhecimento', ''), height=200)
                            nova_comment = st.text_area("Comentários:", value=agente.get('comments', ''), height=200)
                            novo_planejamento = st.text_area("Planejamento:", value=agente.get('planejamento', ''), height=200)
                            
                            submitted = st.form_submit_button("Atualizar Agente")
                            if submitted:
                                if novo_nome:
                                    atualizar_agente(
                                        agente['_id'], 
                                        novo_nome, 
                                        novo_prompt, 
                                        nova_base, 
                                        nova_comment, 
                                        novo_planejamento,
                                        nova_categoria,
                                        agente_mae_id,
                                        herdar_elementos
                                    )
                                    st.success(f"Agente '{novo_nome}' atualizado com sucesso!")
                                    st.rerun()
                                else:
                                    st.error("Nome é obrigatório!")
                else:
                    st.info("Nenhum agente criado ainda.")
            
            with sub_tab3:
                st.subheader("Gerenciar Agentes")
                
                # Filtros por categoria
                categorias = ["Todos", "Social", "SEO", "Conteúdo"]
                categoria_filtro = st.selectbox("Filtrar por categoria:", categorias)
                
                agentes = listar_agentes()
                
                # Aplicar filtro
                if categoria_filtro != "Todos":
                    agentes = [agente for agente in agentes if agente.get('categoria') == categoria_filtro]
                
                if agentes:
                    for i, agente in enumerate(agentes):
                        with st.expander(f"{agente['nome']} - {agente.get('categoria', 'Social')} - Criado em {agente['data_criacao'].strftime('%d/%m/%Y')}"):
                            
                            # Mostrar informações de herança
                            if agente.get('agente_mae_id'):
                                agente_mae = obter_agente(agente['agente_mae_id'])
                                if agente_mae:
                                    st.write(f"**🔗 Herda de:** {agente_mae['nome']}")
                                    st.write(f"**Elementos herdados:** {', '.join(agente.get('herdar_elementos', []))}")
                            
                            st.write(f"**Prompt de Sistema:** {agente['system_prompt'][:100]}..." if agente['system_prompt'] else "**Prompt de Sistema:** (herdado ou vazio)")
                            if agente.get('base_conhecimento'):
                                st.write(f"**Brand Guidelines:** {agente['base_conhecimento'][:200]}...")
                            if agente.get('comments'):
                                st.write(f"**Comentários do cliente:** {agente['comments'][:200]}...")
                            if agente.get('planejamento'):
                                st.write(f"**Planejamento:** {agente['planejamento'][:200]}...")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Selecionar para Chat", key=f"select_{i}"):
                                    st.session_state.agente_selecionado = obter_agente_com_heranca(agente['_id'])
                                    st.session_state.messages = []
                                    st.success(f"Agente '{agente['nome']}' selecionado!")
                            with col2:
                                if st.button("Desativar", key=f"delete_{i}"):
                                    desativar_agente(agente['_id'])
                                    st.success(f"Agente '{agente['nome']}' desativado!")
                                    st.rerun()
                else:
                    st.info("Nenhum agente encontrado para esta categoria.")

with tab_chat:
    st.header("💬 Chat com Agente")
    
    # Seleção de agente se não houver um selecionado
    if not st.session_state.agente_selecionado:
        agentes = listar_agentes()
        if agentes:
            # Agrupar agentes por categoria
            agentes_por_categoria = {}
            for agente in agentes:
                categoria = agente.get('categoria', 'Social')
                if categoria not in agentes_por_categoria:
                    agentes_por_categoria[categoria] = []
                agentes_por_categoria[categoria].append(agente)
            
            # Seleção com agrupamento
            agente_options = {}
            for categoria, agentes_cat in agentes_por_categoria.items():
                for agente in agentes_cat:
                    agente_completo = obter_agente_com_heranca(agente['_id'])
                    display_name = f"{agente['nome']} ({categoria})"
                    if agente.get('agente_mae_id'):
                        display_name += " 🔗"
                    agente_options[display_name] = agente_completo
            
            agente_selecionado_display = st.selectbox("Selecione um agente para conversar:", 
                                                     list(agente_options.keys()))
            
            if st.button("Iniciar Conversa", key="iniciar_chat"):
                st.session_state.agente_selecionado = agente_options[agente_selecionado_display]
                st.session_state.messages = []
                st.rerun()
        else:
            st.info("Nenhum agente disponível. Crie um agente primeiro na aba de Gerenciamento.")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Conversando com: {agente['nome']}")
        
        # Mostrar informações de herança se aplicável
        if 'agente_mae_id' in agente and agente['agente_mae_id']:
            agente_original = obter_agente(agente['_id'])
            if agente_original and agente_original.get('herdar_elementos'):
                st.info(f"🔗 Este agente herda {len(agente_original['herdar_elementos'])} elementos do agente mãe")
        
        # Controles de segmentos na sidebar do chat
        st.sidebar.subheader("🔧 Configurações do Agente")
        st.sidebar.write("Selecione quais bases de conhecimento usar:")
        
        segmentos_disponiveis = {
            "Prompt do Sistema": "system_prompt",
            "Brand Guidelines": "base_conhecimento", 
            "Comentários do Cliente": "comments",
            "Planejamento": "planejamento"
        }
        
        segmentos_selecionados = []
        for nome, chave in segmentos_disponiveis.items():
            if st.sidebar.checkbox(nome, value=chave in st.session_state.segmentos_selecionados, key=f"seg_{chave}"):
                segmentos_selecionados.append(chave)
        
        st.session_state.segmentos_selecionados = segmentos_selecionados
        
        # Exibir status dos segmentos
        if segmentos_selecionados:
            st.sidebar.success(f"✅ Usando {len(segmentos_selecionados)} segmento(s)")
        else:
            st.sidebar.warning("⚠️ Nenhum segmento selecionado")
        
        # Botão para trocar de agente
        if st.button("Trocar de Agente", key="trocar_agente"):
            st.session_state.agente_selecionado = None
            st.session_state.messages = []
            st.rerun()
        
        # Exibir histórico de mensagens
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        
        # Input do usuário
        if prompt := st.chat_input("Digite sua mensagem..."):
            # Adicionar mensagem do usuário ao histórico
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)
            
            # Construir contexto com segmentos selecionados
            contexto = construir_contexto(
                agente, 
                st.session_state.segmentos_selecionados, 
                st.session_state.messages
            )
            
            # Gerar resposta
            with st.chat_message("assistant"):
                with st.spinner('Pensando...'):
                    try:
                        resposta = modelo_texto.generate_content(contexto)
                        st.markdown(resposta.text)
                        
                        # Adicionar ao histórico
                        st.session_state.messages.append({"role": "assistant", "content": resposta.text})
                        
                        # Salvar conversa com segmentos utilizados
                        salvar_conversa(
                            agente['_id'], 
                            st.session_state.messages,
                            st.session_state.segmentos_selecionados
                        )
                        
                    except Exception as e:
                        st.error(f"Erro ao gerar resposta: {str(e)}")

with tab_video:
    st.header("🎬 Validação de Vídeos")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Validação com: {agente['nome']}")
        
        # Controles de segmentos para validação de vídeo
        st.sidebar.subheader("🔧 Configurações de Validação de Vídeo")
        st.sidebar.write("Selecione bases para validação:")
        
        segmentos_video = st.sidebar.multiselect(
            "Bases para validação de vídeo:",
            options=["system_prompt", "base_conhecimento", "comments", "planejamento"],
            default=st.session_state.segmentos_selecionados,
            key="video_segmentos"
        )
        
        # Seleção do tipo de entrada
        entrada_tipo = st.radio(
            "Escolha o tipo de entrada:",
            ["Upload de Arquivo", "URL do YouTube"],
            horizontal=True,
            key="video_input_type"
        )
        
        # Configurações de análise
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            tipo_analise = st.selectbox(
                "Tipo de Análise:",
                ["completa", "rapida", "tecnica"],
                format_func=lambda x: {
                    "completa": "📊 Análise Completa",
                    "rapida": "⚡ Análise Rápida", 
                    "tecnica": "🛠️ Análise Técnica"
                }[x],
                key="tipo_analise"
            )
        
        with col_config2:
            if tipo_analise == "completa":
                st.info("Análise detalhada de todos os aspectos")
            elif tipo_analise == "rapida":
                st.info("Foco nos pontos mais críticos")
            else:
                st.info("Análise técnica e de qualidade")
        
        if entrada_tipo == "Upload de Arquivo":
            st.subheader("📤 Upload de Vídeo")
            
            uploaded_video = st.file_uploader(
                "Carregue o vídeo para análise",
                type=["mp4", "mpeg", "mov", "avi", "flv", "mpg", "webm", "wmv", "3gpp"],
                help="Formatos suportados: MP4, MPEG, MOV, AVI, FLV, MPG, WEBM, WMV, 3GPP",
                key="video_uploader"
            )
            
            if uploaded_video:
                # Exibir informações do vídeo
                st.info(f"📹 Arquice: {uploaded_video.name}")
                st.info(f"📏 Tamanho: {uploaded_video.size / (1024*1024):.2f} MB")
                
                # Exibir preview do vídeo
                st.video(uploaded_video)
                
                # Botão de análise
                if st.button("🎬 Iniciar Análise do Vídeo", type="primary", key="analise_upload"):
                    with st.spinner('Analisando vídeo... Isso pode levar alguns minutos'):
                        resultado = processar_video_upload(
                            uploaded_video, 
                            segmentos_video, 
                            agente, 
                            tipo_analise
                        )
                        
                        st.subheader("📋 Resultado da Análise")
                        st.markdown(resultado)
                        
                        # Opção para download do relatório
                        st.download_button(
                            "💾 Baixar Relatório",
                            data=resultado,
                            file_name=f"relatorio_video_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            key="download_upload"
                        )
        
        else:  # URL do YouTube
            st.subheader("🔗 URL do YouTube")
            
            youtube_url = st.text_input(
                "Cole a URL do vídeo do YouTube:",
                placeholder="https://www.youtube.com/watch?v=...",
                help="A URL deve ser pública (não privada ou não listada)",
                key="youtube_url"
            )
            
            if youtube_url:
                # Validar URL do YouTube
                if "youtube.com" in youtube_url or "youtu.be" in youtube_url:
                    st.success("✅ URL do YouTube válida detectada")
                    
                    # Botão de análise
                    if st.button("🎬 Iniciar Análise do Vídeo", type="primary", key="analise_youtube"):
                        with st.spinner('Analisando vídeo do YouTube... Isso pode levar alguns minutos'):
                            resultado = processar_url_youtube(
                                youtube_url, 
                                segmentos_video, 
                                agente, 
                                tipo_analise
                            )
                            
                            st.subheader("📋 Resultado da Análise")
                            st.markdown(resultado)
                            
                            # Opção para download do relatório
                            st.download_button(
                                "💾 Baixar Relatório",
                                data=resultado,
                                file_name=f"relatorio_youtube_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                mime="text/plain",
                                key="download_youtube"
                            )
                else:
                    st.error("❌ Por favor, insira uma URL válida do YouTube")
        
        # Seção de informações
        with st.expander("ℹ️ Informações sobre Análise de Vídeos"):
            st.markdown("""
            ### 📹 Capacidades de Análise
            
            O agente pode analisar vídeos considerando:
            
            **🎯 Conteúdo e Mensagem:**
            - Alinhamento com diretrizes da marca
            - Clareza da mensagem principal
            - Tom e linguagem apropriados
            - Valores e posicionamento
            
            **🎨 Aspectos Visuais:**
            - Identidade visual (cores, logos, tipografia)
            - Qualidade de produção
            - Consistência da marca
            - Enquadramento e composição
            
            **🔊 Aspectos de Áudio:**
            - Qualidade do áudio
            - Trilha sonora adequada
            - Narração/diálogo claro
            - Mixagem e balanceamento
            
            **📊 Estrutura e Engajamento:**
            - Ritmo e duração apropriados
            - Manutenção do interesse
            - Chamadas para ação eficazes
            - Progressão lógica
            
            ### ⚠️ Limitações Técnicas
            
            - **Duração**: Recomendado até 2 horas para análise completa
            - **Formato**: Formatos comuns de vídeo suportados
            - **Qualidade**: Análise em 1 frame por segundo padrão
            - **YouTube**: Apenas vídeos públicos
            """)

with tab_aprovacao:
    st.header("✅ Validação de Conteúdo")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Validação com: {agente['nome']}")
        
        subtab1, subtab2 = st.tabs(["🖼️ Análise de Imagens", "✍️ Revisão de Textos"])
        
        with subtab1:
            uploaded_image = st.file_uploader("Carregue imagem para análise (.jpg, .png)", type=["jpg", "jpeg", "png"], key="image_upload")
            if uploaded_image:
                st.image(uploaded_image, use_column_width=True, caption="Pré-visualização")
                if st.button("Validar Imagem", key="analyze_img"):
                    with st.spinner('Analisando imagem...'):
                        try:
                            image = Image.open(uploaded_image)
                            img_bytes = io.BytesIO()
                            image.save(img_bytes, format=image.format)
                            
                            prompt_analise = f"""
                            {agente['system_prompt']}
                            
                            Brand Guidelines:
                            ###BEGIN Brand Guidelines###
                            {agente.get('base_conhecimento', '')}
                            ###END Brand Guidelines###

                            Comentários de observação de conteúdo do cliente:
                            ###BEGIN COMMENTS FROM CLIENT###
                            {agente.get('comments', '')}
                            ###END COMMENTS FROM CLIENT###
                            
                            Planejamento:
                            ###BEGIN PLANEJAMENTO###
                            {agente.get('planejamento', '')}
                            ###END PLANEJAMENTO###
                            
                            Analise esta imagem e forneça um parecer detalhado com:
                            - ✅ Pontos positivos
                            - ❌ Pontos que precisam de ajuste
                            - 🛠 Recomendações específicas
                            - Avaliação final (aprovado/reprovado/com observações)
                            """
                            
                            resposta = modelo_vision.generate_content([
                                prompt_analise,
                                {"mime_type": "image/jpeg", "data": img_bytes.getvalue()}
                            ])
                            st.subheader("Resultado da Análise")
                            st.markdown(resposta.text)
                        except Exception as e:
                            st.error(f"Falha na análise: {str(e)}")

        with subtab2:
            texto_input = st.text_area("Insira o texto para validação:", height=200, key="texto_validacao")
            if st.button("Validar Texto", key="validate_text"):
                with st.spinner('Analisando texto...'):
                    prompt_analise = f"""
                    {agente['system_prompt']}
                    
                            Brand Guidelines:
                            ###BEGIN Brand Guidelines###
                            {agente.get('base_conhecimento', '')}
                            ###END Brand Guidelines###

                            Comentários de observação de conteúdo do cliente:
                            ###BEGIN COMMENTS FROM CLIENT###
                            {agente.get('comments', '')}
                            ###END COMMENTS FROM CLIENT###
                    
                            Planejamento:
                            ###BEGIN PLANEJAMENTO###
                            {agente.get('planejamento', '')}
                            ###END PLANEJAMENTO###
                    
                    Analise este texto e forneça um parecer detalhado:
                    
                    Texto a ser analisado:
                    {texto_input}
                    
                    Formato da resposta:
                    ### Análise Geral
                    [resumo da análise]
                    
                    ### Pontos Fortes
                    - [lista de pontos positivos]
                    
                    ### Pontos a Melhorar
                    - [lista de sugestões]
                    
                    ### Recomendações
                    - [ações recomendadas]
                    
                    ### Versão Ajustada (se necessário)
                    [texto revisado]
                    """
                    
                    resposta = modelo_texto.generate_content(prompt_analise)
                    st.subheader("Resultado da Análise")
                    st.markdown(resposta.text)

# ========== ABA: GERAÇÃO DE CONTEÚDO ==========
with tab_geracao:
    st.header("✨ Geração de Conteúdo com Múltiplos Insumos")
    
    # Conexão com MongoDB para briefings
    try:
        client2 = MongoClient("mongodb+srv://gustavoromao3345:RqWFPNOJQfInAW1N@cluster0.5iilj.mongodb.net/auto_doc?retryWrites=true&w=majority&ssl=true&ssl_cert_reqs=CERT_NONE&tlsAllowInvalidCertificates=true")
        db_briefings = client2['briefings_Broto_Tecnologia']
        collection_briefings = db_briefings['briefings']
        mongo_connected_conteudo = True
    except Exception as e:
        st.error(f"Erro na conexão com MongoDB: {str(e)}")
        mongo_connected_conteudo = False

    # Função para extrair texto de diferentes tipos de arquivo
    def extrair_texto_arquivo(arquivo):
        """Extrai texto de diferentes formatos de arquivo"""
        try:
            extensao = arquivo.name.split('.')[-1].lower()
            
            if extensao == 'pdf':
                return extrair_texto_pdf(arquivo)
            elif extensao == 'txt':
                return extrair_texto_txt(arquivo)
            elif extensao in ['pptx', 'ppt']:
                return extrair_texto_pptx(arquivo)
            elif extensao in ['docx', 'doc']:
                return extrair_texto_docx(arquivo)
            else:
                return f"Formato {extensao} não suportado para extração de texto."
                
        except Exception as e:
            return f"Erro ao extrair texto do arquivo {arquivo.name}: {str(e)}"

    def extrair_texto_pdf(arquivo):
        """Extrai texto de arquivos PDF"""
        try:
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(arquivo)
            texto = ""
            for pagina in pdf_reader.pages:
                texto += pagina.extract_text() + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do PDF: {str(e)}"

    def extrair_texto_txt(arquivo):
        """Extrai texto de arquivos TXT"""
        try:
            return arquivo.read().decode('utf-8')
        except:
            try:
                return arquivo.read().decode('latin-1')
            except Exception as e:
                return f"Erro na leitura do TXT: {str(e)}"

    def extrair_texto_pptx(arquivo):
        """Extrai texto de arquivos PowerPoint"""
        try:
            from pptx import Presentation
            import io
            prs = Presentation(io.BytesIO(arquivo.read()))
            texto = ""
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        texto += shape.text + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do PowerPoint: {str(e)}"

    def extrair_texto_docx(arquivo):
        """Extrai texto de arquivos Word"""
        try:
            import docx
            import io
            doc = docx.Document(io.BytesIO(arquivo.read()))
            texto = ""
            for para in doc.paragraphs:
                texto += para.text + "\n"
            return texto
        except Exception as e:
            return f"Erro na leitura do Word: {str(e)}"

    # Layout principal
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📝 Fontes de Conteúdo")
        
        # Opção 1: Upload de múltiplos arquivos
        st.write("**📎 Upload de Arquivos (PDF, TXT, PPTX, DOCX):**")
        arquivos_upload = st.file_uploader(
            "Selecione um ou mais arquivos:",
            type=['pdf', 'txt', 'pptx', 'ppt', 'docx', 'doc'],
            accept_multiple_files=True,
            help="Arquivos serão convertidos para texto e usados como base para geração de conteúdo"
        )
        
        # Processar arquivos uploadados
        textos_arquivos = ""
        if arquivos_upload:
            st.success(f"✅ {len(arquivos_upload)} arquivo(s) carregado(s)")
            
            with st.expander("📋 Visualizar Conteúdo dos Arquivos", expanded=False):
                for i, arquivo in enumerate(arquivos_upload):
                    st.write(f"**{arquivo.name}** ({arquivo.size} bytes)")
                    with st.spinner(f"Processando {arquivo.name}..."):
                        texto_extraido = extrair_texto_arquivo(arquivo)
                        textos_arquivos += f"\n\n--- CONTEÚDO DE {arquivo.name.upper()} ---\n{texto_extraido}"
                        
                        # Mostrar preview
                        if len(texto_extraido) > 500:
                            st.text_area(f"Preview - {arquivo.name}", 
                                       value=texto_extraido[:500] + "...", 
                                       height=100,
                                       key=f"preview_{i}")
                        else:
                            st.text_area(f"Preview - {arquivo.name}", 
                                       value=texto_extraido, 
                                       height=100,
                                       key=f"preview_{i}")
        
        # Opção 2: Selecionar briefing do banco de dados
        st.write("**🗃️ Briefing do Banco de Dados:**")
        if mongo_connected_conteudo:
            briefings_disponiveis = list(collection_briefings.find().sort("data_criacao", -1).limit(20))
            if briefings_disponiveis:
                briefing_options = {f"{briefing['nome_projeto']} ({briefing['tipo']}) - {briefing['data_criacao'].strftime('%d/%m/%Y')}": briefing for briefing in briefings_disponiveis}
                briefing_selecionado = st.selectbox("Escolha um briefing:", list(briefing_options.keys()))
                
                if briefing_selecionado:
                    briefing_data = briefing_options[briefing_selecionado]
                    st.info(f"Briefing selecionado: {briefing_data['nome_projeto']}")
            else:
                st.info("Nenhum briefing encontrado no banco de dados.")
        else:
            st.warning("Conexão com MongoDB não disponível")
        
        # Opção 3: Inserir briefing manualmente
        st.write("**✍️ Briefing Manual:**")
        briefing_manual = st.text_area("Ou cole o briefing completo aqui:", height=150,
                                      placeholder="""Exemplo:
Título: Campanha de Lançamento
Objetivo: Divulgar novo produto
Público-alvo: Empresários...
Pontos-chave: [lista os principais pontos]""")
        
        # Transcrição de áudio/vídeo
        st.write("**🎤 Transcrição de Áudio/Video:**")
        arquivos_midia = st.file_uploader(
            "Áudios/Vídeos para transcrição:",
            type=['mp3', 'wav', 'mp4', 'mov', 'avi'],
            accept_multiple_files=True,
            help="Arquivos de mídia serão transcritos automaticamente"
        )
        
        transcricoes_texto = ""
        if arquivos_midia:
            st.info(f"🎬 {len(arquivos_midia)} arquivo(s) de mídia carregado(s)")
            if st.button("🔄 Transcrever Todos os Arquivos de Mídia"):
                with st.spinner("Transcrevendo arquivos de mídia..."):
                    for arquivo in arquivos_midia:
                        tipo = "audio" if arquivo.type.startswith('audio') else "video"
                        transcricao = transcrever_audio_video(arquivo, tipo)
                        transcricoes_texto += f"\n\n--- TRANSCRIÇÃO DE {arquivo.name.upper()} ---\n{transcricao}"
                        st.success(f"✅ {arquivo.name} transcrito!")
    
    with col2:
        st.subheader("⚙️ Configurações")
        
        tipo_conteudo = st.selectbox("Tipo de Conteúdo:", 
                                   ["Post Social", "Artigo Blog", "Email Marketing", 
                                    "Landing Page", "Script Vídeo", "Relatório Técnico",
                                    "Press Release", "Newsletter", "Case Study"])
        
        tom_voz = st.selectbox("Tom de Voz:", 
                              ["Formal", "Informal", "Persuasivo", "Educativo", 
                               "Inspirador", "Técnico", "Jornalístico"])
        
        palavras_chave = st.text_input("Palavras-chave (opcional):",
                                      placeholder="separadas por vírgula")
        
        numero_palavras = st.slider("Número de Palavras:", 100, 3000, 800)
        
        # Configurações avançadas
        with st.expander("🔧 Configurações Avançadas"):
            usar_contexto_agente = st.checkbox("Usar contexto do agente selecionado", 
                                             value=bool(st.session_state.agente_selecionado))
            
            nivel_detalhe = st.select_slider("Nível de Detalhe:", 
                                           ["Resumido", "Balanceado", "Detalhado", "Completo"])
            
            incluir_cta = st.checkbox("Incluir Call-to-Action", value=True)
            
            formato_saida = st.selectbox("Formato de Saída:", 
                                       ["Texto Simples", "Markdown", "HTML Básico"])

    # Área de instruções específicas
    st.subheader("🎯 Instruções Específicas")
    instrucoes_especificas = st.text_area(
        "Diretrizes adicionais para geração:",
        placeholder="""Exemplos:
- Focar nos benefícios para o usuário final
- Incluir estatísticas quando possível
- Manter linguagem acessível
- Evitar jargões técnicos excessivos
- Seguir estrutura: problema → solução → benefícios""",
        height=100
    )

    # Botão para gerar conteúdo
    if st.button("🚀 Gerar Conteúdo com Todos os Insumos", type="primary", use_container_width=True):
        # Verificar se há pelo menos uma fonte de conteúdo
        tem_conteudo = (arquivos_upload or 
                       briefing_manual or 
                       ('briefing_data' in locals() and briefing_data) or
                       arquivos_midia)
        
        if not tem_conteudo:
            st.error("❌ Por favor, forneça pelo menos uma fonte de conteúdo (arquivos, briefing ou mídia)")
        else:
            with st.spinner("Processando todos os insumos e gerando conteúdo..."):
                try:
                    # Construir o contexto combinado de todas as fontes
                    contexto_completo = "## FONTES DE CONTEÚDO COMBINADAS:\n\n"
                    
                    # Adicionar conteúdo dos arquivos uploadados
                    if textos_arquivos:
                        contexto_completo += "### CONTEÚDO DOS ARQUIVOS:\n" + textos_arquivos + "\n\n"
                    
                    # Adicionar briefing do banco ou manual
                    if briefing_manual:
                        contexto_completo += "### BRIEFING MANUAL:\n" + briefing_manual + "\n\n"
                    elif 'briefing_data' in locals() and briefing_data:
                        contexto_completo += "### BRIEFING DO BANCO:\n" + briefing_data['conteudo'] + "\n\n"
                    
                    # Adicionar transcrições
                    if transcricoes_texto:
                        contexto_completo += "### TRANSCRIÇÕES DE MÍDIA:\n" + transcricoes_texto + "\n\n"
                    
                    # Adicionar contexto do agente se selecionado
                    contexto_agente = ""
                    if usar_contexto_agente and st.session_state.agente_selecionado:
                        agente = st.session_state.agente_selecionado
                        contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                    
                    # Construir prompt final
                    prompt_final = f"""
                    {contexto_agente}
                    
                    ## INSTRUÇÕES PARA GERAÇÃO DE CONTEÚDO:
                    
                    **TIPO DE CONTEÚDO:** {tipo_conteudo}
                    **TOM DE VOZ:** {tom_voz}
                    **PALAVRAS-CHAVE:** {palavras_chave if palavras_chave else 'Não especificadas'}
                    **NÚMERO DE PALAVRAS:** {numero_palavras} (±10%)
                    **NÍVEL DE DETALHE:** {nivel_detalhe}
                    **INCLUIR CALL-TO-ACTION:** {incluir_cta}
                    
                    **INSTRUÇÕES ESPECÍFICAS:**
                    {instrucoes_especificas if instrucoes_especificas else 'Nenhuma instrução específica fornecida.'}
                    
                    ## FONTES E REFERÊNCIAS:
                    {contexto_completo}
                    
                    ## TAREFA:
                    Com base em TODAS as fontes fornecidas acima, gere um conteúdo do tipo {tipo_conteudo} que:
                    
                    1. **Síntese Eficiente:** Combine e sintetize informações de todas as fontes
                    2. **Coerência:** Mantenha consistência com as informações originais
                    3. **Valor Agregado:** Vá além da simples cópia, agregando insights
                    4. **Engajamento:** Crie conteúdo que engaje o público-alvo
                    5. **Clareza:** Comunique ideias complexas de forma acessível
                    
                    **FORMATO DE SAÍDA:** {formato_saida}
                    
                    Gere um conteúdo completo e profissional.
                    """
                    
                    resposta = modelo_texto.generate_content(prompt_final)
                    
                    # Processar saída baseada no formato selecionado
                    conteudo_gerado = resposta.text
                    
                    if formato_saida == "HTML Básico":
                        # Converter markdown para HTML básico
                        import re
                        conteudo_gerado = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'\*(.*?)\*', r'<em>\1</em>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'### (.*?)\n', r'<h3>\1</h3>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'## (.*?)\n', r'<h2>\1</h2>', conteudo_gerado)
                        conteudo_gerado = re.sub(r'# (.*?)\n', r'<h1>\1</h1>', conteudo_gerado)
                        conteudo_gerado = conteudo_gerado.replace('\n', '<br>')
                    
                    st.subheader("📄 Conteúdo Gerado")
                    
                    if formato_saida == "HTML Básico":
                        st.components.v1.html(conteudo_gerado, height=400, scrolling=True)
                    else:
                        st.markdown(conteudo_gerado)
                    
                    # Estatísticas
                    palavras_count = len(conteudo_gerado.split())
                    col_stat1, col_stat2, col_stat3 = st.columns(3)
                    with col_stat1:
                        st.metric("Palavras Geradas", palavras_count)
                    with col_stat2:
                        st.metric("Arquivos Processados", len(arquivos_upload) if arquivos_upload else 0)
                    with col_stat3:
                        st.metric("Fontes Utilizadas", 
                                 (1 if arquivos_upload else 0) + 
                                 (1 if briefing_manual or 'briefing_data' in locals() else 0) +
                                 (1 if transcricoes_texto else 0))
                    
                    # Botões de download
                    extensao = ".html" if formato_saida == "HTML Básico" else ".md" if formato_saida == "Markdown" else ".txt"
                    
                    st.download_button(
                        f"💾 Baixar Conteúdo ({formato_saida})",
                        data=conteudo_gerado,
                        file_name=f"conteudo_gerado_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}{extensao}",
                        mime="text/html" if formato_saida == "HTML Básico" else "text/plain"
                    )
                    
                    # Salvar no histórico se MongoDB disponível
                    if mongo_connected_conteudo:
                        try:
                            from bson import ObjectId
                            historico_data = {
                                "tipo_conteudo": tipo_conteudo,
                                "tom_voz": tom_voz,
                                "palavras_chave": palavras_chave,
                                "numero_palavras": numero_palavras,
                                "conteudo_gerado": conteudo_gerado,
                                "fontes_utilizadas": {
                                    "arquivos_upload": [arquivo.name for arquivo in arquivos_upload] if arquivos_upload else [],
                                    "briefing_manual": bool(briefing_manual),
                                    "transcricoes": len(arquivos_midia) if arquivos_midia else 0
                                },
                                "data_criacao": datetime.datetime.now()
                            }
                            db_briefings['historico_geracao'].insert_one(historico_data)
                            st.success("✅ Conteúdo salvo no histórico!")
                        except Exception as e:
                            st.warning(f"Conteúdo gerado, mas não salvo no histórico: {str(e)}")
                    
                except Exception as e:
                    st.error(f"❌ Erro ao gerar conteúdo: {str(e)}")
                    st.info("💡 Dica: Verifique se os arquivos não estão corrompidos e tente novamente.")

    # Seção de histórico rápido
    if mongo_connected_conteudo:
        with st.expander("📚 Histórico de Gerações Recentes"):
            try:
                historico = list(db_briefings['historico_geracao'].find().sort("data_criacao", -1).limit(5))
                if historico:
                    for item in historico:
                        st.write(f"**{item['tipo_conteudo']}** - {item['data_criacao'].strftime('%d/%m/%Y %H:%M')}")
                        st.caption(f"Palavras-chave: {item.get('palavras_chave', 'Nenhuma')} | Tom: {item['tom_voz']}")
                        with st.expander("Ver conteúdo"):
                            st.write(item['conteudo_gerado'][:500] + "..." if len(item['conteudo_gerado']) > 500 else item['conteudo_gerado'])
                else:
                    st.info("Nenhuma geração no histórico")
            except Exception as e:
                st.warning(f"Erro ao carregar histórico: {str(e)}")

with tab_resumo:
    st.header("📝 Resumo de Textos")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Resumo com: {agente['nome']}")
        
        col_original, col_resumo = st.columns(2)
        
        with col_original:
            st.subheader("Texto Original")
            texto_original = st.text_area(
                "Cole o texto que deseja resumir:",
                height=400,
                placeholder="Insira aqui o texto completo...",
                key="texto_original"
            )
            
            with st.expander("⚙️ Configurações do Resumo"):
                nivel_resumo = st.select_slider(
                    "Nível de Resumo:",
                    options=["Extenso", "Moderado", "Conciso"],
                    value="Moderado",
                    key="nivel_resumo"
                )
                
                incluir_pontos = st.checkbox(
                    "Incluir pontos-chave em tópicos",
                    value=True,
                    key="incluir_pontos"
                )
                
                manter_terminologia = st.checkbox(
                    "Manter terminologia técnica",
                    value=True,
                    key="manter_terminologia"
                )
        
        with col_resumo:
            st.subheader("Resumo Gerado")
            
            if st.button("Gerar Resumo", key="gerar_resumo"):
                if not texto_original.strip():
                    st.warning("Por favor, insira um texto para resumir")
                else:
                    with st.spinner("Processando resumo..."):
                        try:
                            config_resumo = {
                                "Extenso": "um resumo detalhado mantendo cerca de 50% do conteúdo original",
                                "Moderado": "um resumo conciso mantendo cerca de 30% do conteúdo original",
                                "Conciso": "um resumo muito breve com apenas os pontos essenciais (cerca de 10-15%)"
                            }[nivel_resumo]
                            
                            prompt = f"""
                            {agente['system_prompt']}
                            
                            Brand Guidelines:
                            {agente.get('base_conhecimento', '')}
                            
                            Planejamento:
                            {agente.get('planejamento', '')}
                            
                            Crie um resumo deste texto com as seguintes características:
                            - {config_resumo}
                            - {"Inclua os principais pontos em tópicos" if incluir_pontos else "Formato de texto contínuo"}
                            - {"Mantenha a terminologia técnica específica" if manter_terminologia else "Simplifique a linguagem"}
                            
                            Texto para resumir:
                            {texto_original}
                            
                            Estrutura do resumo:
                            1. Título do resumo
                            2. {"Principais pontos em tópicos" if incluir_pontos else "Resumo textual"}
                            3. Conclusão/Recomendações
                            """
                            
                            resposta = modelo_texto.generate_content(prompt)
                            st.markdown(resposta.text)
                            
                            st.download_button(
                                "📋 Copiar Resumo",
                                data=resposta.text,
                                file_name="resumo_gerado.txt",
                                mime="text/plain",
                                key="download_resumo"
                            )
                            
                        except Exception as e:
                            st.error(f"Erro ao gerar resumo: {str(e)}")

with tab_busca:
    st.header("🌐 Busca Web com Perplexity")
    
    if not perp_api_key:
        st.error("❌ Chave da API Perplexity não encontrada. Configure a variável de ambiente PERP_API_KEY.")
    else:
        st.success("✅ API Perplexity configurada com sucesso!")
        
        # Seleção de modo de busca
        modo_busca = st.radio(
            "Selecione o modo de busca:",
            ["🔍 Busca Geral na Web", "📋 Análise de URLs Específicas"],
            horizontal=True,
            key="modo_busca"
        )
        
        # Configurações comuns
        col_config1, col_config2 = st.columns(2)
        
        with col_config1:
            usar_agente = st.checkbox(
                "Usar contexto do agente selecionado",
                value=st.session_state.agente_selecionado is not None,
                help="Utilizar o conhecimento do agente para contextualizar a busca",
                key="usar_agente_busca"
            )
        
        with col_config2:
            if usar_agente and st.session_state.agente_selecionado:
                agente = st.session_state.agente_selecionado
                st.info(f"🎯 Usando: {agente['nome']}")
            else:
                st.info("🔍 Busca sem contexto específico")
        
        if modo_busca == "🔍 Busca Geral na Web":
            st.subheader("Busca Geral na Web")
            
            pergunta = st.text_area(
                "Digite sua pergunta para busca:",
                placeholder="Ex: Quais são as últimas tendências em marketing digital para 2024?",
                height=100,
                key="pergunta_geral"
            )
            
            # Configurações avançadas
            with st.expander("⚙️ Configurações Avançadas"):
                col_adv1, col_adv2 = st.columns(2)
                
                with col_adv1:
                    max_tokens = st.slider(
                        "Comprimento da resposta:",
                        min_value=500,
                        max_value=3000,
                        value=1500,
                        step=100,
                        key="max_tokens_geral"
                    )
                
                with col_adv2:
                    temperatura = st.slider(
                        "Criatividade:",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.1,
                        step=0.1,
                        key="temp_geral"
                    )
            
            if st.button("🔎 Realizar Busca", type="primary", key="buscar_geral"):
                if not pergunta.strip():
                    st.warning("⚠️ Por favor, digite uma pergunta para busca.")
                else:
                    with st.spinner("🔄 Buscando informações na web..."):
                        # Construir contexto do agente se selecionado
                        contexto_agente = None
                        if usar_agente and st.session_state.agente_selecionado:
                            agente = st.session_state.agente_selecionado
                            contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                        
                        resultado = buscar_perplexity(
                            pergunta=pergunta,
                            contexto_agente=contexto_agente
                        )
                        
                        st.subheader("📋 Resultado da Busca")
                        st.markdown(resultado)
                        
                        # Opção para download
                        st.download_button(
                            "💾 Baixar Resultado",
                            data=resultado,
                            file_name=f"busca_web_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                            mime="text/plain",
                            key="download_busca_geral"
                        )
        
        else:  # Análise de URLs Específicas
            st.subheader("Análise de URLs Específicas")
            
            urls_input = st.text_area(
                "Cole as URLs para análise (uma por linha):",
                placeholder="https://exemplo.com/artigo1\nhttps://exemplo.com/artigo2\nhttps://exemplo.com/noticia",
                height=150,
                key="urls_input",
                help="Insira uma URL por linha. Máximo de 5 URLs por análise."
            )
            
            pergunta_urls = st.text_area(
                "Digite a pergunta específica para análise:",
                placeholder="Ex: Com base nestas URLs, quais são os pontos principais discutidos?",
                height=100,
                key="pergunta_urls"
            )
            
            if st.button("🔍 Analisar URLs", type="primary", key="analisar_urls"):
                if not urls_input.strip() or not pergunta_urls.strip():
                    st.warning("⚠️ Por favor, preencha tanto as URLs quanto a pergunta.")
                else:
                    # Processar URLs
                    urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
                    
                    if len(urls) > 5:
                        st.warning("⚠️ Muitas URLs. Analisando apenas as primeiras 5.")
                        urls = urls[:5]
                    
                    # Validar URLs
                    urls_validas = []
                    for url in urls:
                        if url.startswith(('http://', 'https://')):
                            urls_validas.append(url)
                        else:
                            st.warning(f"URL inválida (falta http:// ou https://): {url}")
                    
                    if not urls_validas:
                        st.error("❌ Nenhuma URL válida encontrada.")
                    else:
                        with st.spinner(f"🔄 Analisando {len(urls_validas)} URL(s)..."):
                            # Construir contexto do agente se selecionado
                            contexto_agente = None
                            if usar_agente and st.session_state.agente_selecionado:
                                agente = st.session_state.agente_selecionado
                                contexto_agente = construir_contexto(agente, st.session_state.segmentos_selecionados)
                            
                            resultado = analisar_urls_perplexity(
                                urls=urls_validas,
                                pergunta=pergunta_urls,
                                contexto_agente=contexto_agente
                            )
                            
                            st.subheader("📋 Resultado da Análise")
                            st.markdown(resultado)
                            
                            # Mostrar URLs analisadas
                            st.info("### 🌐 URLs Analisadas:")
                            for i, url in enumerate(urls_validas, 1):
                                st.write(f"{i}. {url}")
                            
                            # Opção para download
                            st.download_button(
                                "💾 Baixar Análise",
                                data=resultado,
                                file_name=f"analise_urls_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                mime="text/plain",
                                key="download_analise_urls"
                            )
        
        # Seção de informações
        with st.expander("ℹ️ Informações sobre Busca Web"):
            st.markdown("""
            ### 🌐 Capacidades da Busca Web
            
            **Busca Geral:**
            - Pesquisa em tempo real na web
            - Informações atualizadas
            - Citações de fontes confiáveis
            - Respostas contextuais
            
            **Análise de URLs:**
            - Leitura e análise de páginas específicas
            - Comparação entre múltiplas fontes
            - Extração de pontos principais
            - Síntese de informações
            
            ### ⚡ Tecnologia Utilizada
            
            - **Motor**: Perplexity AI Sonar Medium Online
            - **Atualização**: Dados em tempo real
            - **Fontes**: Diversas fontes confiáveis da web
            - **Citações**: Inclui referências às fontes
            
            ### 💡 Dicas de Uso
            
            - Para buscas gerais, seja específico na pergunta
            - Use o contexto do agente para respostas mais relevantes
            - Para URLs, prefira páginas com conteúdo textual
            - Limite de 5 URLs por análise para melhor performance
            """)

# --- ABA: OTIMIZAÇÃO SEO ---
with tab_seo:
    st.header("🚀 Otimização de Conteúdo SEO")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        
        # Verificar se o agente selecionado é da categoria SEO
        if agente.get('categoria') != 'SEO':
            st.warning("⚠️ Esta funcionalidade é otimizada para agentes da categoria SEO.")
            st.info("💡 Para melhor desempenho, selecione um agente específico para SEO na aba de Chat.")
        
        st.subheader(f"Otimização com: {agente['nome']}")
        
        # Layout em colunas para organização
        col_config, col_conteudo = st.columns([1, 2])
        
        with col_config:
            st.subheader("⚙️ Configurações SEO")
            
            # Tipo de conteúdo
            tipo_conteudo = st.selectbox(
                "Tipo de Conteúdo:",
                ["blog", "landing page", "página de produto", "artigo", "notícia", "guia"],
                help="Selecione o tipo de conteúdo para análise específica",
                key="tipo_conteudo_seo"
            )
            
            # Palavra-chave principal
            palavra_chave_principal = st.text_input(
                "Palavra-chave Principal (opcional):",
                placeholder="Ex: marketing digital",
                help="Deixe em branco para o agente identificar automaticamente",
                key="palavra_chave_seo"
            )
            
            # Configurações de análise
            with st.expander("🔧 Configurações Avançadas"):
                analise_competitiva = st.checkbox(
                    "Incluir análise competitiva",
                    value=True,
                    help="Sugerir estratégias baseadas em concorrentes",
                    key="analise_competitiva"
                )
                
                sugestoes_conteudo = st.checkbox(
                    "Gerar sugestões de conteúdo relacionado",
                    value=True,
                    help="Sugerir tópicos relacionados para pillar content",
                    key="sugestoes_conteudo"
                )
                
                checklist_acao = st.checkbox(
                    "Incluir checklist de ações",
                    value=True,
                    help="Gerar lista de tarefas para implementação",
                    key="checklist_acao"
                )
        
        with col_conteudo:
            st.subheader("📝 Conteúdo para Otimização")
            
            conteudo_para_analise = st.text_area(
                "Cole o conteúdo que deseja otimizar para SEO:",
                height=400,
                placeholder="Cole aqui o texto completo do seu conteúdo...\n\nInclua títulos, subtítulos e corpo do texto.",
                help="Quanto mais completo o conteúdo, mais detalhada será a análise SEO",
                key="conteudo_seo"
            )
            
            # Estatísticas do conteúdo
            if conteudo_para_analise:
                palavras = len(conteudo_para_analise.split())
                caracteres = len(conteudo_para_analise)
                paragrafos = conteudo_para_analise.count('\n\n') + 1
                
                col_stats1, col_stats2, col_stats3 = st.columns(3)
                with col_stats1:
                    st.metric("📊 Palavras", palavras)
                with col_stats2:
                    st.metric("🔤 Caracteres", caracteres)
                with col_stats3:
                    st.metric("📄 Parágrafos", paragrafos)
            
            # Botão de análise
            if st.button("🚀 Gerar Análise SEO Completa", type="primary", key="analise_seo"):
                if not conteudo_para_analise.strip():
                    st.warning("⚠️ Por favor, cole o conteúdo que deseja otimizar.")
                else:
                    with st.spinner("🔄 Analisando conteúdo e gerando relatório SEO..."):
                        try:
                            resultado = gerar_analise_seo(
                                conteudo=conteudo_para_analise,
                                agente=agente,
                                palavra_chave_principal=palavra_chave_principal if palavra_chave_principal else None,
                                tipo_conteudo=tipo_conteudo
                            )
                            
                            st.subheader("📋 Relatório de Otimização SEO")
                            st.markdown(resultado)
                            
                            # Opções de download
                            col_dl1, col_dl2 = st.columns(2)
                            
                            with col_dl1:
                                st.download_button(
                                    "💾 Baixar Relatório Completo",
                                    data=resultado,
                                    file_name=f"relatorio_seo_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                    mime="text/plain",
                                    key="download_seo_completo"
                                )
                            
                            with col_dl2:
                                # Extrair apenas o checklist se disponível
                                if "### 📋 CHECKLIST DE OTIMIZAÇÃO" in resultado:
                                    checklist_start = resultado.find("### 📋 CHECKLIST DE OTIMIZAÇÃO")
                                    checklist_end = resultado.find("###", checklist_start + 1)
                                    checklist = resultado[checklist_start:checklist_end] if checklist_end != -1 else resultado[checklist_start:]
                                    
                                    st.download_button(
                                        "📋 Baixar Checklist",
                                        data=checklist,
                                        file_name=f"checklist_seo_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                        mime="text/plain",
                                        key="download_checklist_seo"
                                    )
                            
                        except Exception as e:
                            st.error(f"❌ Erro ao gerar análise SEO: {str(e)}")
        
        # Seção informativa
        with st.expander("ℹ️ Sobre a Análise SEO"):
            st.markdown("""
            ### 🎯 O que é Analisado
            
            **🔍 Análise de Palavras-chave:**
            - Identificação de palavras-chave principais e secundárias
            - Densidade e distribuição no conteúdo
            - Sugestões de palavras-chave LSI (Latent Semantic Indexing)
            
            **📝 Otimização On-Page:**
            - Meta título e description
            - Estrutura de headings (H1, H2, H3)
            - Comprimento e qualidade do conteúdo
            - Legibilidade e engajamento
            
            **🔗 Elementos Técnicos:**
            - Estrutura de URLs
            - Otimização de imagens (alt text)
            - Links internos e externos
            - Chamadas para ação (CTAs)
            
            **📈 Estratégias Off-Page:**
            - Link building
            - Compartilhamento em redes sociais
            - Conteúdo relacionado
            
            ### 📊 Métricas de Qualidade
            
            - **Score SEO**: Pontuação geral de 0-40
            - **Conteúdo**: Valor, profundidade e originalidade
            - **Técnico**: Elementos técnicos de SEO
            - **Experiência do Usuário**: Engajamento e usabilidade
            
            ### 💡 Dicas para Melhor Análise
            
            1. **Conteúdo Completo**: Cole o texto integral para análise detalhada
            2. **Palavra-chave**: Especifique a palavra-chave principal quando possível
            3. **Contexto**: Use agentes da categoria SEO para melhores resultados
            4. **Implementação**: Siga o checklist gerado para otimização prática
            """)

# --- NOVA ABA: REVISÃO ORTOGRÁFICA ---
with tab_revisao:
    st.header("📝 Revisão Ortográfica e Gramatical")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Revisão com: {agente['nome']}")
        
        # Configurações de segmentos para revisão
        st.sidebar.subheader("🔧 Configurações de Revisão")
        st.sidebar.write("Selecione bases para orientar a revisão:")
        
        segmentos_revisao = st.sidebar.multiselect(
            "Bases para revisão:",
            options=["system_prompt", "base_conhecimento", "comments", "planejamento"],
            default=st.session_state.segmentos_selecionados,
            key="revisao_segmentos"
        )
        
        # Layout em colunas
        col_original, col_resultado = st.columns(2)
        
        with col_original:
            st.subheader("📄 Texto Original")
            
            texto_para_revisao = st.text_area(
                "Cole o texto que deseja revisar:",
                height=400,
                placeholder="Cole aqui o texto que precisa de revisão ortográfica e gramatical...",
                help="O texto será analisado considerando as diretrizes do agente selecionado",
                key="texto_revisao"
            )
            
            # Estatísticas do texto
            if texto_para_revisao:
                palavras = len(texto_para_revisao.split())
                caracteres = len(texto_para_revisao)
                paragrafos = texto_para_revisao.count('\n\n') + 1
                
                col_stats1, col_stats2, col_stats3 = st.columns(3)
                with col_stats1:
                    st.metric("📊 Palavras", palavras)
                with col_stats2:
                    st.metric("🔤 Caracteres", caracteres)
                with col_stats3:
                    st.metric("📄 Parágrafos", paragrafos)
            
            # Configurações de revisão
            with st.expander("⚙️ Configurações da Revisão"):
                revisao_estilo = st.checkbox(
                    "Incluir revisão de estilo",
                    value=True,
                    help="Analisar clareza, coesão e adequação ao tom da marca",
                    key="revisao_estilo"
                )
                
                manter_estrutura = st.checkbox(
                    "Manter estrutura original",
                    value=True,
                    help="Preservar a estrutura geral do texto quando possível",
                    key="manter_estrutura"
                )
                
                explicar_alteracoes = st.checkbox(
                    "Explicar alterações principais",
                    value=True,
                    help="Incluir justificativa para as mudanças mais importantes",
                    key="explicar_alteracoes"
                )
        
        with col_resultado:
            st.subheader("📋 Resultado da Revisão")
            
            if st.button("🔍 Realizar Revisão Completa", type="primary", key="revisar_texto"):
                if not texto_para_revisao.strip():
                    st.warning("⚠️ Por favor, cole o texto que deseja revisar.")
                else:
                    with st.spinner("🔄 Analisando texto e realizando revisão..."):
                        try:
                            resultado = revisar_texto_ortografia(
                                texto=texto_para_revisao,
                                agente=agente,
                                segmentos_selecionados=segmentos_revisao
                            )
                            
                            st.markdown(resultado)
                            
                            # Opções de download
                            col_dl1, col_dl2, col_dl3 = st.columns(3)
                            
                            with col_dl1:
                                st.download_button(
                                    "💾 Baixar Relatório Completo",
                                    data=resultado,
                                    file_name=f"relatorio_revisao_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                    mime="text/plain",
                                    key="download_revisao_completo"
                                )
                            
                            with col_dl2:
                                # Extrair apenas o texto revisado se disponível
                                if "## 📋 TEXTO REVISADO" in resultado:
                                    texto_revisado_start = resultado.find("## 📋 TEXTO REVISADO")
                                    texto_revisado_end = resultado.find("##", texto_revisado_start + 1)
                                    texto_revisado = resultado[texto_revisado_start:texto_revisado_end] if texto_revisado_end != -1 else resultado[texto_revisado_start:]
                                    
                                    st.download_button(
                                        "📄 Baixar Texto Revisado",
                                        data=texto_revisado,
                                        file_name=f"texto_revisado_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                        mime="text/plain",
                                        key="download_texto_revisado"
                                    )
                            
                            with col_dl3:
                                # Extrair apenas as explicações se disponível
                                if "## 🔍 EXPLICAÇÃO DAS PRINCIPAIS ALTERAÇÕES" in resultado:
                                    explicacoes_start = resultado.find("## 🔍 EXPLICAÇÃO DAS PRINCIPAIS ALTERAÇÕES")
                                    explicacoes_end = resultado.find("##", explicacoes_start + 1)
                                    explicacoes = resultado[explicacoes_start:explicacoes_end] if explicacoes_end != -1 else resultado[explicacoes_start:]
                                    
                                    st.download_button(
                                        "📝 Baixar Explicações",
                                        data=explicacoes,
                                        file_name=f"explicacoes_revisao_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                        mime="text/plain",
                                        key="download_explicacoes"
                                    )
                            
                        except Exception as e:
                            st.error(f"❌ Erro ao realizar revisão: {str(e)}")
        
        # Seção informativa
        with st.expander("ℹ️ Sobre a Revisão Ortográfica"):
            st.markdown("""
            ### 🎯 O que é Analisado
            
            **🔤 Ortografia:**
            - Erros de grafia e acentuação
            - Uso correto de maiúsculas e minúsculas
            - Escrita de números e datas
            - Concordância nominal e verbal
            
            **📖 Gramática:**
            - Estrutura sintática das frases
            - Uso adequado de preposições
            - Colocação pronominal
            - Regência verbal e nominal
            
            **🔠 Pontuação:**
            - Uso de vírgulas, pontos, dois-pontos
            - Aplicação de travessões e parênteses
            - Pontuação de citações e diálogos
            
            **📝 Estilo e Clareza:**
            - Coesão e coerência textual
            - Adequação ao tom da marca
            - Clareza na comunicação
            - Eliminação de vícios de linguagem
            
            ### 📊 Métricas de Qualidade
            
            - **Ortografia**: Correção gramatical (0-10)
            - **Gramática**: Estrutura linguística (0-10)
            - **Clareza**: Facilidade de compreensão (0-10)
            - **Conformidade**: Adequação às diretrizes (0-10)
            - **Total**: Pontuação geral (0-40)
            
            ### 💡 Dicas para Melhor Revisão
            
            1. **Texto Completo**: Cole o texto integral para análise detalhada
            2. **Segmentos Relevantes**: Selecione as bases de conhecimento apropriadas
            3. **Contexto Específico**: Use agentes especializados para cada tipo de conteúdo
            4. **Implementação**: Aplique as sugestões sistematicamente
            
            ### 🎨 Benefícios da Revisão Contextual
            
            - **Consistência da Marca**: Mantém o tom e estilo adequados
            - **Qualidade Profissional**: Elimina erros que prejudicam a credibilidade
            - **Otimização de Conteúdo**: Melhora a clareza e impacto da comunicação
            - **Eficiência**: Reduz tempo de revisão manual
            """)

# --- Estilização ---
st.markdown("""
<style>
    .stChatMessage {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    [data-testid="stChatMessageContent"] {
        font-size: 1rem;
    }
    .stChatInput {
        bottom: 20px;
        position: fixed;
        width: calc(100% - 5rem);
    }
    div[data-testid="stTabs"] {
        margin-top: -30px;
    }
    div[data-testid="stVerticalBlock"] > div:has(>.stTextArea) {
        border-left: 3px solid #4CAF50;
        padding-left: 1rem;
    }
    .segment-indicator {
        background-color: #f0f2f6;
        padding: 0.5rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
        border-left: 4px solid #4CAF50;
    }
    .video-analysis-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .inheritance-badge {
        background-color: #e3f2fd;
        color: #1976d2;
        padding: 0.2rem 0.5rem;
        border-radius: 12px;
        font-size: 0.8rem;
        margin-left: 0.5rem;
    }
    .web-search-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .seo-analysis-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    .spelling-review-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)
