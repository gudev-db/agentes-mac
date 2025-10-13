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
import PyPDF2
from pptx import Presentation
import docx

def mostrar_aba_gerenciamento():
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
                mostrar_subaba_criar_agente()
            
            with sub_tab2:
                mostrar_subaba_editar_agente()
            
            with sub_tab3:
                mostrar_subaba_gerenciar_agentes()

def mostrar_subaba_criar_agente():
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

def mostrar_subaba_editar_agente():
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

def mostrar_subaba_gerenciar_agentes():
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
