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
import re

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
collection_comentarios = db['comentarios']
collection_editorias = db['editorias']

# Configuração da API do Gemini
gemini_api_key = os.getenv("GEM_API_KEY")
if not gemini_api_key:
    st.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente")
    st.stop()

genai.configure(api_key=gemini_api_key)
modelo_vision = genai.GenerativeModel("gemini-2.5-flash", generation_config={"temperature": 0.1})
modelo_texto = genai.GenerativeModel("gemini-2.5-flash")

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
def criar_agente(nome, system_prompt, base_conhecimento):
    """Cria um novo agente no MongoDB"""
    agente = {
        "nome": nome,
        "system_prompt": system_prompt,
        "base_conhecimento": base_conhecimento,
        "segmentos_base": {
            "dos_donts": "",
            "planejamento": "",
            "referencias": "",
            "tecnicas": ""
        },
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

def atualizar_agente(agente_id, nome, system_prompt, base_conhecimento, segmentos_base):
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
                "segmentos_base": segmentos_base,
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

def salvar_conversa(agente_id, mensagens, incluir_na_base=False):
    """Salva uma conversa no histórico"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    conversa = {
        "agente_id": agente_id,
        "mensagens": mensagens,
        "data_criacao": datetime.datetime.now(),
        "incluir_na_base": incluir_na_base
    }
    return collection_conversas.insert_one(conversa)

def obter_conversas(agente_id, limite=10, incluir_na_base=None):
    """Obtém o histórico de conversas de um agente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    
    query = {"agente_id": agente_id}
    if incluir_na_base is not None:
        query["incluir_na_base"] = incluir_na_base
    
    return list(collection_conversas.find(query).sort("data_criacao", -1).limit(limite))

# --- Funções para Comentários do Cliente ---
def salvar_comentario(agente_id, comentario, tipo="feedback", prioridade="media"):
    """Salva um comentário do cliente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    
    comentario_doc = {
        "agente_id": agente_id,
        "comentario": comentario,
        "tipo": tipo,
        "prioridade": prioridade,
        "data_criacao": datetime.datetime.now(),
        "status": "pendente"
    }
    result = collection_comentarios.insert_one(comentario_doc)
    return result.inserted_id

def listar_comentarios(agente_id, status=None):
    """Lista comentários de um agente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    
    query = {"agente_id": agente_id}
    if status:
        query["status"] = status
    
    return list(collection_comentarios.find(query).sort("data_criacao", -1))

def processar_comentarios_com_llm(comentarios):
    """Processa comentários com LLM para extrair regras"""
    if not comentarios:
        return ""
    
    texto_comentarios = "\n".join([f"- {c['comentario']} (Prioridade: {c['prioridade']})" for c in comentarios])
    
    prompt = f"""
    Analise os seguintes comentários de clientes e extraia regras, diretrizes e padrões gerais que podem ser aplicados na base de conhecimento.
    
    COMENTÁRIOS:
    {texto_comentarios}
    
    Extraia:
    1. Regras explícitas mencionadas
    2. Preferências de estilo/tom
    3. Elementos a serem evitados
    4. Elementos a serem priorizados
    5. Padrões de qualidade esperados
    
    Formate a resposta como uma lista clara de diretrizes que podem ser adicionadas à base de conhecimento.
    """
    
    try:
        resposta = modelo_texto.generate_content(prompt)
        return resposta.text
    except Exception as e:
        st.error(f"Erro ao processar comentários: {str(e)}")
        return ""

# --- Funções para Editorias/Legendas ---
def salvar_editoria(agente_id, titulo, conteudo, tags=[]):
    """Salva uma editoria/legenda aprovada"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    
    editoria = {
        "agente_id": agente_id,
        "titulo": titulo,
        "conteudo": conteudo,
        "tags": tags,
        "data_criacao": datetime.datetime.now(),
        "aprovada": True
    }
    result = collection_editorias.insert_one(editoria)
    return result.inserted_id

def listar_editorias(agente_id, tags=None):
    """Lista editorias de um agente"""
    if isinstance(agente_id, str):
        agente_id = ObjectId(agente_id)
    
    query = {"agente_id": agente_id, "aprovada": True}
    if tags:
        query["tags"] = {"$in": tags}
    
    return list(collection_editorias.find(query).sort("data_criacao", -1))

def extrair_padroes_editorias(editorias):
    """Extrai padrões das editorias aprovadas usando LLM"""
    if not editorias:
        return ""
    
    texto_editorias = "\n".join([f"Título: {e['titulo']}\nConteúdo: {e['conteudo']}\nTags: {', '.join(e['tags'])}\n---" for e in editorias])
    
    prompt = f"""
    Analise as seguintes editorias/legendas aprovadas e identifique padrões, estruturas e características comuns que podem ser transformadas em diretrizes para a base de conhecimento.
    
    EDITORIAS APROVADAS:
    {texto_editorias}
    
    Identifique:
    1. Estruturas de título bem-sucedidas
    2. Padrões de formatação
    3. Tom de voz consistente
    4. Elementos de engajamento
    5. Características de conteúdo aprovado
    6. Padrões de uso de hashtags
    7. Estruturas de chamada para ação
    
    Formate como diretrizes práticas para criação de conteúdo.
    """
    
    try:
        resposta = modelo_texto.generate_content(prompt)
        return resposta.text
    except Exception as e:
        st.error(f"Erro ao extrair padrões: {str(e)}")
        return ""

# --- Função para Construir Contexto do Agente ---
def construir_contexto_agente(agente, segmentos_ativos=None):
    """Constrói o contexto completo do agente incluindo bases selecionadas"""
    contexto = agente['system_prompt'] + "\n\n"
    
    # Base de conhecimento principal (como estava antes)
    if agente.get('base_conhecimento'):
        contexto += "BASE DE CONHECIMENTO PRINCIPAL:\n"
        contexto += agente['base_conhecimento'] + "\n\n"
    
    # Segmentos de base de conhecimento
    if segmentos_ativos and agente.get('segmentos_base'):
        for segmento in segmentos_ativos:
            if segmento in agente['segmentos_base'] and agente['segmentos_base'][segmento]:
                contexto += f"--- {segmento.upper()} ---\n"
                contexto += agente['segmentos_base'][segmento] + "\n\n"
    
    return contexto

# --- Interface Principal ---
st.sidebar.title(f"🤖 Bem-vindo, {st.session_state.user}!")

# Botão de logout na sidebar
if st.sidebar.button("🚪 Sair"):
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
if "segmentos_ativos" not in st.session_state:
    st.session_state.segmentos_ativos = []

# Menu de abas
tab_chat, tab_gerenciamento, tab_base_conhecimento, tab_comentarios, tab_editorias, tab_aprovacao, tab_geracao, tab_resumo = st.tabs([
    "💬 Chat", 
    "⚙️ Gerenciar Agentes", 
    "📚 Base de Conhecimento",
    "💬 Comentários",
    "📝 Editorias",
    "✅ Validação", 
    "✨ Geração de Conteúdo",
    "📄 Resumo de Textos"
])

with tab_gerenciamento:
    st.header("Gerenciamento de Agentes")
    
    if st.session_state.user != "admin":
        st.warning("Acesso restrito a administradores")
    else:
        if not check_admin_password():
            st.warning("Digite a senha de administrador")
        else:
            if st.button("Logout Admin"):
                if "admin_password_correct" in st.session_state:
                    del st.session_state["admin_password_correct"]
                if "admin_user" in st.session_state:
                    del st.session_state["admin_user"]
                st.rerun()
            
            st.write(f'Bem-vindo administrador!')
            
            sub_tab1, sub_tab2, sub_tab3 = st.tabs(["Criar Agente", "Editar Agente", "Gerenciar Agentes"])
            
            with sub_tab1:
                st.subheader("Criar Novo Agente")
                
                with st.form("form_criar_agente"):
                    nome_agente = st.text_input("Nome do Agente:")
                    system_prompt = st.text_area("Prompt de Sistema:", height=150,
                                                placeholder="Ex: Você é um assistente especializado em...")
                    base_conhecimento = st.text_area("Base de Conhecimento:", height=200,
                                                   placeholder="Cole aqui informações, diretrizes, dados...")
                    
                    submitted = st.form_submit_button("Criar Agente")
                    if submitted:
                        if nome_agente and system_prompt:
                            agente_id = criar_agente(nome_agente, system_prompt, base_conhecimento)
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
                            novo_prompt = st.text_area("Prompt de Sistema:", value=agente['system_prompt'], height=150)
                            nova_base = st.text_area("Base de Conhecimento:", value=agente.get('base_conhecimento', ''), height=200)
                            
                            submitted = st.form_submit_button("Atualizar Agente")
                            if submitted:
                                if novo_nome and novo_prompt:
                                    atualizar_agente(agente['_id'], novo_nome, novo_prompt, nova_base, agente.get('segmentos_base', {}))
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
                            st.write(f"**Prompt de Sistema:** {agente['system_prompt']}")
                            if agente.get('base_conhecimento'):
                                st.write(f"**Base de Conhecimento:** {agente['base_conhecimento'][:200]}...")
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button("Selecionar para Chat", key=f"select_{agente['_id']}"):
                                    st.session_state.agente_selecionado = agente
                                    st.session_state.messages = []
                                    st.session_state.segmentos_ativos = []
                                    st.success(f"Agente '{agente['nome']}' selecionado!")
                            with col2:
                                if st.button("Desativar", key=f"delete_{agente['_id']}"):
                                    desativar_agente(agente['_id'])
                                    st.success(f"Agente '{agente['nome']}' desativado!")
                                    st.rerun()
                else:
                    st.info("Nenhum agente criado ainda.")

with tab_base_conhecimento:
    st.header("📚 Gerenciamento de Base de Conhecimento Segmentada")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        
        st.subheader(f"Segmentos de Base para: {agente['nome']}")
        
        # Inicializar segmentos se não existirem
        if 'segmentos_base' not in agente:
            agente['segmentos_base'] = {
                "dos_donts": "",
                "planejamento": "",
                "referencias": "",
                "tecnicas": ""
            }
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Base Principal (como antes)")
            base_principal = st.text_area(
                "Base de Conhecimento Principal:",
                value=agente.get('base_conhecimento', ''),
                height=300,
                placeholder="Base principal como funcionava antes..."
            )
            
            if st.button("Atualizar Base Principal"):
                if st.session_state.user == "admin" and check_admin_password():
                    atualizar_agente(
                        agente['_id'], 
                        agente['nome'], 
                        agente['system_prompt'], 
                        base_principal,
                        agente.get('segmentos_base', {})
                    )
                    st.success("Base principal atualizada!")
                    st.rerun()
                else:
                    st.error("Apenas administradores podem atualizar a base principal")
        
        with col2:
            st.subheader("Segmentos Específicos")
            
            segmentos = {
                "dos_donts": "Dos e Don'ts - Regras e Restrições",
                "planejamento": "Planejamento - Estratégias e Metodologias", 
                "referencias": "Referências - Fontes e Exemplos",
                "tecnicas": "Técnicas - Métodos e Processos"
            }
            
            for segmento_key, segmento_desc in segmentos.items():
                st.write(f"**{segmento_desc}**")
                conteudo_segmento = st.text_area(
                    f"Conteúdo do {segmento_desc}:",
                    value=agente['segmentos_base'].get(segmento_key, ''),
                    height=150,
                    key=f"seg_{segmento_key}"
                )
                
                if st.button(f"Atualizar {segmento_desc}", key=f"btn_{segmento_key}"):
                    if st.session_state.user == "admin" and check_admin_password():
                        novos_segmentos = agente['segmentos_base'].copy()
                        novos_segmentos[segmento_key] = conteudo_segmento
                        atualizar_agente(
                            agente['_id'],
                            agente['nome'],
                            agente['system_prompt'],
                            agente.get('base_conhecimento', ''),
                            novos_segmentos
                        )
                        st.success(f"{segmento_desc} atualizado!")
                        st.rerun()
                    else:
                        st.error("Apenas administradores podem atualizar segmentos")

with tab_comentarios:
    st.header("💬 Comentários do Cliente")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Novo Comentário")
            with st.form("form_comentario"):
                comentario = st.text_area("Comentário/Feedback:", height=150,
                                        placeholder="Digite o comentário do cliente...")
                tipo = st.selectbox("Tipo:", ["feedback", "critica", "sugestao"])
                prioridade = st.selectbox("Prioridade:", ["baixa", "media", "alta"])
                
                submitted = st.form_submit_button("Salvar Comentário")
                if submitted and comentario:
                    salvar_comentario(agente['_id'], comentario, tipo, prioridade)
                    st.success("Comentário salvo com sucesso!")
        
        with col2:
            st.subheader("Comentários Existentes")
            comentarios = listar_comentarios(agente['_id'])
            
            if comentarios:
                # Botão para processar comentários
                if st.button("🔄 Extrair Regras dos Comentários"):
                    with st.spinner("Processando comentários..."):
                        regras_extraidas = processar_comentarios_com_llm(comentarios)
                        if regras_extraidas:
                            st.subheader("Regras Extraídas:")
                            st.text_area("Regras extraídas:", value=regras_extraidas, height=200, key="regras_extraidas")
                            
                            if st.button("Adicionar ao Segmento Dos e Don'ts"):
                                if st.session_state.user == "admin" and check_admin_password():
                                    novos_segmentos = agente.get('segmentos_base', {}).copy()
                                    novos_segmentos['dos_donts'] = agente['segmentos_base'].get('dos_donts', '') + "\n\n" + regras_extraidas
                                    atualizar_agente(
                                        agente['_id'],
                                        agente['nome'],
                                        agente['system_prompt'],
                                        agente.get('base_conhecimento', ''),
                                        novos_segmentos
                                    )
                                    st.success("Regras adicionadas ao segmento Dos e Don'ts!")
                                    st.rerun()
                                else:
                                    st.error("Apenas administradores podem atualizar a base")
                
                for comentario in comentarios:
                    cor_prioridade = {
                        "baixa": "🟢",
                        "media": "🟡", 
                        "alta": "🔴"
                    }
                    
                    with st.expander(f"{cor_prioridade[comentario['prioridade']]} {comentario['tipo']} - {comentario['data_criacao'].strftime('%d/%m/%Y')}"):
                        st.write(comentario['comentario'])
                        st.write(f"**Status:** {comentario['status']}")
            else:
                st.info("Nenhum comentário registrado ainda.")

with tab_editorias:
    st.header("📝 Editorias e Legendas Aprovadas")
    
    if not st.session_state.agente_selecionado:
        st.info("Selecione um agente primeiro na aba de Chat")
    else:
        agente = st.session_state.agente_selecionado
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Nova Editoria/Legenda")
            with st.form("form_editoria"):
                titulo = st.text_input("Título:")
                conteudo = st.text_area("Conteúdo:", height=200,
                                      placeholder="Digite o conteúdo aprovado...")
                tags = st.text_input("Tags (separadas por vírgula):")
                
                submitted = st.form_submit_button("Salvar Editoria")
                if submitted and titulo and conteudo:
                    tags_list = [tag.strip() for tag in tags.split(",")] if tags else []
                    salvar_editoria(agente['_id'], titulo, conteudo, tags_list)
                    st.success("Editoria salva com sucesso!")
        
        with col2:
            st.subheader("Editorias Existentes")
            editorias = listar_editorias(agente['_id'])
            
            if editorias:
                # Botão para extrair padrões
                if st.button("🔄 Extrair Padrões das Editorias"):
                    with st.spinner("Analisando padrões..."):
                        padroes_extraidos = extrair_padroes_editorias(editorias)
                        if padroes_extraidos:
                            st.subheader("Padrões Extraídos:")
                            st.text_area("Padrões encontrados:", value=padroes_extraidos, height=200, key="padroes_editorias")
                            
                            if st.button("Adicionar Padrões ao Segmento Técnicas"):
                                if st.session_state.user == "admin" and check_admin_password():
                                    novos_segmentos = agente.get('segmentos_base', {}).copy()
                                    novos_segmentos['tecnicas'] = agente['segmentos_base'].get('tecnicas', '') + "\n\n" + padroes_extraidos
                                    atualizar_agente(
                                        agente['_id'],
                                        agente['nome'],
                                        agente['system_prompt'],
                                        agente.get('base_conhecimento', ''),
                                        novos_segmentos
                                    )
                                    st.success("Padrões adicionados ao segmento Técnicas!")
                                    st.rerun()
                                else:
                                    st.error("Apenas administradores podem atualizar a base")
                
                for editoria in editorias:
                    with st.expander(f"{editoria['titulo']} - {editoria['data_criacao'].strftime('%d/%m/%Y')}"):
                        st.write(editoria['conteudo'])
                        if editoria['tags']:
                            st.write(f"**Tags:** {', '.join(editoria['tags'])}")
            else:
                st.info("Nenhuma editoria salva ainda.")

with tab_chat:
    st.header("💬 Chat com Agente")
    
    if not st.session_state.agente_selecionado:
        agentes = listar_agentes()
        if agentes:
            agente_options = {agente['nome']: agente for agente in agentes}
            agente_selecionado_nome = st.selectbox("Selecione um agente para conversar:", 
                                                 list(agente_options.keys()))
            
            if st.button("Iniciar Conversa"):
                st.session_state.agente_selecionado = agente_options[agente_selecionado_nome]
                st.session_state.messages = []
                st.session_state.segmentos_ativos = []
                st.rerun()
        else:
            st.info("Nenhum agente disponível. Crie um agente primeiro na aba de Gerenciamento.")
    else:
        agente = st.session_state.agente_selecionado
        st.subheader(f"Conversando com: {agente['nome']}")
        
        # Controles de segmentos de base de conhecimento na sidebar
        st.sidebar.subheader("📚 Segmentos de Base de Conhecimento")
        
        # Segmentos disponíveis
        segmentos_disponiveis = {
            "dos_donts": "📋 Dos e Don'ts",
            "planejamento": "📊 Planejamento", 
            "referencias": "🔗 Referências",
            "tecnicas": "🛠️ Técnicas"
        }
        
        for segmento_key, segmento_nome in segmentos_disponiveis.items():
            # Verificar se o segmento tem conteúdo
            tem_conteudo = (agente.get('segmentos_base', {}).get(segmento_key, '') != '')
            
            if tem_conteudo:
                checked = st.sidebar.checkbox(
                    segmento_nome,
                    value=(segmento_key in st.session_state.segmentos_ativos),
                    key=f"seg_{segmento_key}"
                )
                if checked and segmento_key not in st.session_state.segmentos_ativos:
                    st.session_state.segmentos_ativos.append(segmento_key)
                elif not checked and segmento_key in st.session_state.segmentos_ativos:
                    st.session_state.segmentos_ativos.remove(segmento_key)
            else:
                st.sidebar.write(f"⭕ {segmento_nome} (vazio)")
        
        # Mostrar base principal sempre ativa
        st.sidebar.write("---")
        st.sidebar.write("✅ Base Principal (sempre ativa)")
        
        # Opção para incluir conversa na base
        incluir_na_base = st.sidebar.checkbox("💾 Incluir esta conversa na base de conhecimento")
        
        # Botão para trocar de agente
        if st.button("Trocar de Agente"):
            st.session_state.agente_selecionado = None
            st.session_state.messages = []
            st.session_state.segmentos_ativos = []
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
            
            # Construir contexto com segmentos ativos (mantendo a base principal como antes)
            contexto = construir_contexto_agente(agente, st.session_state.segmentos_ativos)
            
            # Adicionar histórico formatado
            contexto += "\n\nHistórico da conversa:"
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
                        salvar_conversa(agente['_id'], st.session_state.messages, incluir_na_base)
                        
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
                            {agente['system_prompt']}
                            
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
                    {agente['system_prompt']}
                    
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
                    {agente['system_prompt']}
                    
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
                    {agente['system_prompt']}
                    
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
                            {agente['system_prompt']}
                            
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
