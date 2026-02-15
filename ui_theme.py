import streamlit as st


import streamlit as st


def inject_global_css() -> None:
    """CSS base compartilhado por todas as páginas (dark mode + layout)."""
    st.markdown(
        """
        <style>
        /* ============================
           Painéis genéricos e pílulas
        ============================ */

        /* Painel genérico (usado em PDF Setup, etc.) */
        .rijks-panel {
            background-color: #181818;
            border-radius: 12px;
            padding: 1.0rem 1.25rem 1.1rem 1.25rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 1px solid #262626;
            margin-bottom: 1.3rem;
        }

        /* Pílula-resumo (contadores, contexto rápido) */
        .rijks-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 999px;
            background-color: #262626;
            color: #f5f5f5;
            font-size: 0.85rem;
            margin-top: 0.25rem;
            margin-bottom: 0.9rem;
        }
        .rijks-pill strong { color: #ff9900; }

        /* ============================
           Layout e cores globais
        ============================ */
        .stApp {
            background-color: #111111;
            color: #f5f5f5;
        }

        /* Área central de conteúdo */
        div.block-container {
            max-width: 95vw;
            padding-left: 2rem;
            padding-right: 2rem;
            padding-top: 1.3rem;   /* respiro no topo */
            padding-bottom: 2.5rem;
        }

        @media (min-width: 1400px) {
            div.block-container {
                padding-left: 3rem;
                padding-right: 3rem;
            }
        }

        /* Evita que o primeiro elemento grude no topo
           (resolve o problema do título “escondido”) */
        div.block-container > *:first-child {
            margin-top: 0.5rem;
        }

        /* Sidebar em dark mode */
        section[data-testid="stSidebar"] {
            background-color: #181818 !important;
        }

        /* ============================
           Tipografia básica
        ============================ */
        h1, h2, h3 {
            font-weight: 600;
        }

        h2 {
            font-size: 1.5rem;
            margin-top: 0.5rem;
            margin-bottom: 0.75rem;
        }

        h3 {
            font-size: 1.15rem;
            margin-top: 1.25rem;
            margin-bottom: 0.5rem;
        }

        /* Links padrão do app */
        div[data-testid="stMarkdownContainer"] a {
            color: #ff9900 !important;
            text-decoration: none;
        }
        div[data-testid="stMarkdownContainer"] a:hover {
            text-decoration: underline;
        }
        /* ============================
           Bloco de introdução de página
        ============================ */
        .page-intro-wrapper {
            margin-top: 0.7rem;
            margin-bottom: 1.1rem;
        }

        .page-intro-title {
            font-weight: 600;
            font-size: 1.0rem;
            margin-bottom: 0.4rem;
        }

        .page-intro-list {
            margin-top: 0;
            margin-bottom: 0;
            padding-left: 1.2rem;
        }

        /* ============================
           Rodapé global
        ============================ */
        .rijks-footer {
            margin-top: 2.5rem;
            padding-top: 0.75rem;
            border-top: 1px solid #262626;
            font-size: 0.8rem;
            color: #aaaaaa;
            text-align: center;
        }
        
        /* Título principal da sidebar (HOME) */
        .rijks-sidebar-main-title {
            font-size: 1.0rem;
            font-weight: 600;
            padding: 0.3rem 0.3rem 0.35rem 0.4rem;
            margin-bottom: 0.75rem;
            line-height: 1.2;
        }
        
        </style>
        """,
        unsafe_allow_html=True,
    )

def show_page_intro(title: str, bullets: list[str]) -> None:
    """Bloco padrão de introdução no topo de cada página."""
    items_html = "".join(f"<li>{b}</li>" for b in bullets)
    st.markdown(
        f"""
        <div class="page-intro-wrapper">
            <p class="page-intro-title">{title}</p>
            <ul class="page-intro-list">
                {items_html}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_global_footer() -> None:
    """Rodapé padrão para todas as páginas."""
    st.markdown(
        """
        <div class="rijks-footer">
            Rijksmuseum Explorer — prototype created for study & research purposes.<br>
            Data & images provided by the Rijksmuseum Data Services.
        </div>
        """,
        unsafe_allow_html=True,
    )