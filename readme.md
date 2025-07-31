Oi pessoal 👋, 

Esse projeto aqui nasceu meio que como um desafio pessoal de consolidar análises de vendas de um dataset conhecido (Olist) mas de um jeito bonito (ou pelo menos tentei kkk) e funcional. É um dashboard web com Flask + Pandas + Plotly, que mostra métricas, gráficos e permite exportar relatórios (CSV e PDF).

---

## 🎯 Objetivo

A ideia é ter **uma visão rápida das vendas entregues**, com:
- KPIs (Receita, Pedidos, Ticket Médio)
- Top categorias de produto
- Evolução mensal
- Pedidos por UF
- Exportação de relatórios pra CSV e PDF

E o mais importante: tudo **na mesma tela**, sem precisar rolar (desktop) e com responsividade no mobile.

---

## 🛠 Tecnologias utilizadas

- Python 3.10+  
- [Flask](https://flask.palletsprojects.com/) (framework web)
- [Pandas](https://pandas.pydata.org/) (tratamento dos dados)
- [Plotly](https://plotly.com/python/) (gráficos lindões)
- [ReportLab](https://www.reportlab.com/) (PDF)
- [Kaleido](https://github.com/plotly/Kaleido) (renderizar gráficos no PDF)

> *Obs:* fiquei horas tentando o Kaleido no Windows... se você tiver problema, manda um café e respira fundo que a gente resolve rsrs

---

## 🚀 Como rodar

1. Clone este repositório:
   ```bash
   git clone https://github.com/seu-usuario/advpy.git
   cd advpy