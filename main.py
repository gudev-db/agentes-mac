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

# Configuração inicial
st.set_page_config(
    layout="wide",
    page_title="Agente Generativo",
    page_icon="🤖"
)

# Conexão com MongoDB
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
modelo_vision = genai.GenerativeModel("gemini-1.5-flash", generation_config={"temperature": 0.1})
modelo_texto = genai.GenerativeModel("gemini-1.5-flash")

# --- Configuração de Autenticação Simples ---
def check_password():
    """Retorna True se o usuário fornecer a senha correta."""
    
    def password_entered():
        """Verifica se a senha está correta."""
        if st.session_state["password"] == "senha123":
            st.session_state["password_correct"] = True
            st.session_state["user"] = "admin"
            del st.session_state["password"]  # Não armazena a senha
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # Mostra o input para senha primeiro
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Senha incorreta, mostra input + erro
        st.text_input(
            "Senha", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Senha incorreta")
        return False
    else:
        # Senha correta
        return True

# --- Funções CRUD para Agentes ---
def criar_agente(nome, prompt_sistema, base_conhecimento):
    """Cria um novo agente no MongoDB"""
    agente = {
        "nome": nome,
        "system_prompt": prompt_sistema,
        "base_conhecimento": base_conhecimento,
        "data_criacao": datetime.datetime.now(),
        "ativo": True
    }
    result = collection_agentes.insert_one(agente)
    return result.inserted_id

def listar_agentes():
    """Retorna todos os agentes ativos"""
    return list(collection_agentes.find({"ativo": True}).sort("data_criacao", -1))

def obter_agente(agente_id):
    """Obtém um agente específico pelo ID"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.find_one({"_id": agente_id})

def atualizar_agente(agente_id, nome, prompt_sistema, base_conhecimento):
    """Atualiza um agente existente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    return collection_agentes.update_one(
        {"_id": agente_id},
        {
            "$set": {
                "nome": nome,
                "prompt_sistema": prompt_sistema,
                "base_conhecimento": base_conhecimento,
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

def salvar_conversa(agente_id, mensagens):
    """Salva uma conversa no histórico"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    conversa = {
        "agente_id": agente_id,
        "mensagens": mensagens,
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

# --- Interface Principal ---
st.title("🤖 Agente Generativo Personalizável")

# Inicializar estado da sessão
if "agente_selecionado" not in st.session_state:
    st.session_state.agente_selecionado = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# Menu de abas
tab_chat, tab_gerenciamento, tab_aprovacao, tab_geracao, tab_resumo = st.tabs([
    "💬 Chat", 
    "⚙️ Gerenciar Agentes", 
    "✅ Validação", 
    "✨ Geração de Conteúdo",
    "📝 Resumo de Textos"
])

with tab_gerenciamento:
    st.header("Gerenciamento de Agentes")
    
    # Verificar autenticação apenas para gerenciamento
    if not check_password():
        st.warning("Acesso restrito a administradores")
    else:
        # Mostra o botão de logout
        if st.button("Logout"):
            for key in ["password_correct", "user"]:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
        
        st.write(f'Bem-vindo administrador!')
        
        # Subabas para gerenciamento
        sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Criar Agente", "Editar Agente", "Gerenciar Agentes"])
        
        with sub_tab1:
            st.subheader("Criar Novo Agente")
            
            with st.form("form_criar_agente"):
                nome_agente = st.text_input("Nome do Agente:")
                prompt_sistema = st.text_area("Prompt de Sistema:", height=150, 
                                            placeholder="Ex: Você é um assistente especializado em...")
                base_conhecimento = st.text_area("Base de Conhecimento:", height=200,
                                               placeholder="Cole aqui informações, diretrizes, dados...")
                
                submitted = st.form_submit_button("Criar Agente")
                if submitted:
                    if nome_agente and prompt_sistema:
                        agente_id = criar_agente(nome_agente, prompt_sistema, base_conhecimento)
                        st.success(f"Agente '{nome_agente}' criado com sucesso!")
                    else:
                        st.error("Nome e Prompt de Sistema são obrigatórios!")
        
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
                        novo_prompt = st.text_area("Prompt de Sistema:", value=agente['prompt_sistema'], height=150)
                        nova_base = st.text_area("Base de Conhecimento:", value=agente.get('base_conhecimento', ''), height=200)
                        
                        submitted = st.form_submit_button("Atualizar Agente")
                        if submitted:
                            if novo_nome and novo_prompt:
                                atualizar_agente(agente['_id'], novo_nome, novo_prompt, nova_base)
                                st.success(f"Agente '{novo_nome}' atualizado com sucesso!")
                                st.rerun()
                            else:
                                st.error("Nome e Prompt de Sistema são obrigatórios!")
            else:
                st.info("Nenhum agente criado ainda.")
        
        with sub_tab3:
            st.subheader("Gerenciar Agentes")
            
            agentes = listar_agentes()
            if agentes:
                for agente in agentes:
                    with st.expander(f"{agente['nome']} - Criado em {agente['data_criacao'].strftime('%d/%m/%Y')}"):
                        st.write(f"**Prompt de Sistema:** {agente['prompt_sistema']}")
                        if agente.get('base_conhecimento'):
                            st.write(f"**Base de Conhecimento:** {agente['base_conhecimento'][:200]}...")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("Selecionar para Chat", key=f"select_{agente['_id']}"):
                                st.session_state.agente_selecionado = agente
                                st.session_state.messages = []
                                st.success(f"Agente '{agente['nome']}' selecionado!")
                        with col2:
                            if st.button("Desativar", key=f"delete_{agente['_id']}"):
                                desativar_agente(agente['_id'])
                                st.success(f"Agente '{agente['nome']}' desativado!")
                                st.rerun()
            else:
                st.info("Nenhum agente criado ainda.")

with tab_chat:
    st.header("💬 Chat com Agente")
    
    # Seleção de agente se não houver um selecionado
    if not st.session_state.agente_selecionado:
        agentes = listar_agentes()
        if agentes:
            agente_options = {agente['nome']: agente for agente in agentes}
            agente_selecionado_nome = st.selectbox("Selecione um agente para conversar:", 
                                                 list(agente_options.keys()))
            
            if st.button("Iniciar Conversa"):
                st.session_state.agente_selecionado = agente_options[agente_selecionado_nome]
                st.session_state.messages = []
                st.rerun()
        else:
            st.info("Nenhum agente disponível. Crie um agente primeiro na aba de Gerenciamento.")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Conversando com: {agente['nome']}")
        
        # Botão para trocar de agente
        if st.button("Trocar de Agente"):
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
            
            # Preparar contexto com prompt do sistema e base de conhecimento
            contexto = f"""
            {agente['prompt_sistema']}
            
            Base de conhecimento:
            {agente.get('base_conhecimento', '')}
            
            Histórico da conversa:
            """
            
            # Adicionar histórico formatado
            for msg in st.session_state.messages:
                contexto += f"\n{msg['role']}: {msg['content']}"
            
            contexto += "\n\nassistant:"
            
            # Gerar resposta
            with st.chat_message("assistant"):
                with st.spinner('Pensando...'):
                    try:
                        resposta = modelo_texto.generate_content(contexto)
                        st.markdown(resposta.text)
                        
                        # Adicionar ao histórico
                        st.session_state.messages.append({"role": "assistant", "content": resposta.text})
                        
                        # Salvar conversa
                        salvar_conversa(agente['_id'], st.session_state.messages)
                        
                    except Exception as e:
                        st.error(f"Erro ao gerar resposta: {str(e)}")

with tab_aprovacao:
    st.header("✅ Validação de Conteúdo")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Validação com: {agente['nome']}")
        
        subtab1, subtab2 = st.tabs(["🖼️ Análise de Imagens", "✍️ Revisão de Textos"])
        
        with subtab1:
            uploaded_image = st.file_uploader("Carregue imagem para análise (.jpg, .png)", type=["jpg", "jpeg", "png"])
            if uploaded_image:
                st.image(uploaded_image, use_column_width=True, caption="Pré-visualização")
                if st.button("Validar Imagem", key="analyze_img"):
                    with st.spinner('Analisando imagem...'):
                        try:
                            image = Image.open(uploaded_image)
                            img_bytes = io.BytesIO()
                            image.save(img_bytes, format=image.format)
                            
                            prompt_analise = f"""
                            {agente['prompt_sistema']}
                            
                            Base de conhecimento:
                            {agente.get('base_conhecimento', '')}
                            
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
            texto_input = st.text_area("Insira o texto para validação:", height=200)
            if st.button("Validar Texto", key="validate_text"):
                with st.spinner('Analisando texto...'):
                    prompt_analise = f"""
                    {agente['prompt_sistema']}
                    
                    Base de conhecimento:
                    {agente.get('base_conhecimento', '')}
                    
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

with tab_geracao:
    st.header("✨ Geração de Conteúdo")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Geração com: {agente['nome']}")
        
        campanha_brief = st.text_area("Briefing criativo:", help="Descreva objetivos, tom de voz e especificações", height=150)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Diretrizes Visuais")
            if st.button("Gerar Especificações Visuais", key="gen_visual"):
                with st.spinner('Criando guia de estilo...'):
                    prompt = f"""
                    {agente['prompt_sistema']}
                    
                    Base de conhecimento:
                    {agente.get('base_conhecimento', '')}
                    
                    Com base no briefing: {campanha_brief}
                    
                    Crie um manual técnico para designers incluindo:
                    1. 🎨 Paleta de cores (códigos HEX/RGB)
                    2. 🖼️ Diretrizes de fotografia/ilustração
                    3. ✏️ Tipografia hierárquica
                    4. 📐 Grid e proporções recomendadas
                    5. ⚠️ Restrições de uso
                    6. 🖌️ Descrição da imagem principal sugerida
                    7. 📱 Adaptações para diferentes formatos
                    """
                    resposta = modelo_texto.generate_content(prompt)
                    st.markdown(resposta.text)

        with col2:
            st.subheader("Copywriting")
            if st.button("Gerar Textos", key="gen_copy"):
                with st.spinner('Desenvolvendo conteúdo textual...'):
                    prompt = f"""
                    {agente['prompt_sistema']}
                    
                    Base de conhecimento:
                    {agente.get('base_conhecimento', '')}
                    
                    Com base no briefing: {campanha_brief}
                    
                    Crie textos para campanha incluindo:
                    - 📝 Legenda principal (com emojis e quebras de linha)
                    - 🏷️ 10 hashtags relevantes
                    - 🔗 Sugestão de link (se aplicável)
                    - 📢 CTA adequado ao objetivo
                    - 🎯 3 opções de headline
                    - 📄 Corpo de texto (200 caracteres)
                    """
                    resposta = modelo_texto.generate_content(prompt)
                    st.markdown(resposta.text)

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
                placeholder="Insira aqui o texto completo..."
            )
            
            with st.expander("⚙️ Configurações do Resumo"):
                nivel_resumo = st.select_slider(
                    "Nível de Resumo:",
                    options=["Extenso", "Moderado", "Conciso"],
                    value="Moderado"
                )
                
                incluir_pontos = st.checkbox(
                    "Incluir pontos-chave em tópicos",
                    value=True
                )
                
                manter_terminologia = st.checkbox(
                    "Manter terminologia técnica",
                    value=True
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
                            {agente['prompt_sistema']}
                            
                            Base de conhecimento:
                            {agente.get('base_conhecimento', '')}
                            
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
                                mime="text/plain"
                            )
                            
                        except Exception as e:
                            st.error(f"Erro ao gerar resumo: {str(e)}")

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
</style>
""", unsafe_allow_html=True)
