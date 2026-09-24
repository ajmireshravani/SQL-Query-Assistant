import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
from google import genai
import os
import re
import plotly.express as px

# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="AI SQL Query Assistant",
    page_icon="🤖",
    layout="wide"
)

# =========================================================
# ENVIRONMENT
# =========================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("GEMINI_API_KEY is missing from your .env file.")
    st.stop()

client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-3.6-flash"

# =========================================================
# MYSQL
# =========================================================

engine = create_engine(
    "mysql+mysqlconnector://root:root@localhost/ai_sql_assistant"
)

# =========================================================
# SESSION STATE
# =========================================================

if "history" not in st.session_state:
    st.session_state.history = []

if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

if "question_input" not in st.session_state:
    st.session_state.question_input = ""

# =========================================================
# TITLE
# =========================================================

st.title("🤖 AI-Powered SQL Query Assistant")

st.write(
    "Upload your dataset, ask questions in natural language, "
    "and get SQL queries with explanations and visualizations."
)

# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.header("⚙️ Settings")

    chart_choice = st.selectbox(
        "Chart Type",
        ["Automatic", "Bar", "Pie", "Line"]
    )

    st.divider()

    st.header("🕘 Query History")

    if st.session_state.history:

        for i, item in enumerate(
            reversed(st.session_state.history),
            1
        ):
            st.write(
                f"**{i}.** {item['question']}"
            )

    else:
        st.write("No queries yet.")

# =========================================================
# UPLOAD DATASET
# =========================================================

uploaded_file = st.file_uploader(
    "📂 Upload CSV or Excel Dataset",
    type=["csv", "xlsx"]
)

if uploaded_file is not None:

    try:

        # -------------------------------------------------
        # READ DATA
        # -------------------------------------------------

        if uploaded_file.name.lower().endswith(".csv"):

            try:
                df = pd.read_csv(
                    uploaded_file,
                    encoding="utf-8"
                )

            except UnicodeDecodeError:

                uploaded_file.seek(0)

                df = pd.read_csv(
                    uploaded_file,
                    encoding="latin1"
                )

        else:

            df = pd.read_excel(uploaded_file)

        # Remove empty columns
        df = df.dropna(
            axis=1,
            how="all"
        )

        if df.empty:

            st.error("The uploaded dataset is empty.")
            st.stop()

        # Clean column names
        df.columns = [
            str(col).strip()
            for col in df.columns
        ]

        # -------------------------------------------------
        # SAVE TO MYSQL
        # -------------------------------------------------

        df.to_sql(
            "uploaded_data",
            engine,
            if_exists="replace",
            index=False
        )

        st.success(
            "✅ Dataset uploaded and saved to MySQL successfully!"
        )

        # -------------------------------------------------
        # DATASET INFORMATION
        # -------------------------------------------------

        c1, c2, c3 = st.columns(3)

        with c1:
            st.metric(
                "Rows",
                len(df)
            )

        with c2:
            st.metric(
                "Columns",
                len(df.columns)
            )

        with c3:
            st.metric(
                "Missing Values",
                int(df.isnull().sum().sum())
            )

        # -------------------------------------------------
        # DATA PREVIEW
        # -------------------------------------------------

        with st.expander("👀 Preview Dataset"):

            st.dataframe(
                df.head(10),
                use_container_width=True
            )

        # =================================================
        # GENERATE DATASET-SPECIFIC SUGGESTIONS
        # =================================================

        columns = ", ".join(
            [str(col) for col in df.columns]
        )

        sample_data = df.head(5).to_string(
            index=False
        )

        suggestion_prompt = f"""
You are a professional Data Analyst.

Analyze this dataset.

Table:
uploaded_data

Columns:
{columns}

Sample data:
{sample_data}

Generate exactly 6 useful questions that a Data Analyst
could ask about this dataset.

Rules:
- Questions must use the available columns.
- Do not mention columns that do not exist.
- Include different types of analysis.
- Keep questions short.
- Return ONLY the questions.
- Put each question on a separate line.
"""

        try:

            suggestion_response = client.models.generate_content(
                model=MODEL_NAME,
                contents=suggestion_prompt
            )

            suggestion_text = (
                suggestion_response.text or ""
            ).strip()

            suggestions = []

            for line in suggestion_text.splitlines():

                line = re.sub(
                    r"^[\d\-\*\.\)\s]+",
                    "",
                    line
                ).strip()

                if line:
                    suggestions.append(line)

            st.session_state.suggestions = suggestions[:6]

        except Exception:

            st.session_state.suggestions = [
                "What is the total number of records?",
                "What are the main statistics in this dataset?",
                "Which values occur most frequently?",
                "What is the distribution of the data?",
                "What are the top categories?",
                "Can you summarize this dataset?"
            ]

        # =================================================
        # SUGGESTION BOX
        # =================================================

        st.subheader("💡 Suggested Questions")

        st.caption(
            "Questions generated according to your dataset."
        )

        suggestions = st.session_state.suggestions

        for i in range(0, len(suggestions), 2):

            col1, col2 = st.columns(2)

            if i < len(suggestions):

                with col1:

                    if st.button(
                        suggestions[i],
                        key=f"suggestion_{i}",
                        use_container_width=True
                    ):

                        st.session_state.question_input = (
                            suggestions[i]
                        )

            if i + 1 < len(suggestions):

                with col2:

                    if st.button(
                        suggestions[i + 1],
                        key=f"suggestion_{i+1}",
                        use_container_width=True
                    ):

                        st.session_state.question_input = (
                            suggestions[i + 1]
                        )

    except Exception as e:

        st.error(
            f"Error while loading dataset: {e}"
        )

# =========================================================
# QUESTION INPUT
# =========================================================

question = st.text_input(
    "💬 Ask a question about your data:",
    key="question_input",
    placeholder="Example: Which category has the highest sales?"
)

# =========================================================
# PROCESS QUESTION
# =========================================================

if uploaded_file is not None and question.strip():

    try:

        # -------------------------------------------------
        # COLUMN INFORMATION
        # -------------------------------------------------

        columns = ", ".join(
            [str(col) for col in df.columns]
        )

        # -------------------------------------------------
        # GENERATE SQL
        # -------------------------------------------------

        sql_prompt = f"""
You are an expert MySQL Data Analyst.

Table:
uploaded_data

Available columns:
{columns}

User question:
{question}

Generate ONLY one valid MySQL SELECT query.

Rules:
- Use only uploaded_data.
- Use only available columns.
- Do not use INSERT.
- Do not use UPDATE.
- Do not use DELETE.
- Do not use DROP.
- Do not use ALTER.
- Do not use CREATE.
- Do not use TRUNCATE.
- Do not use REPLACE.
- Do not use multiple statements.
- Do not use markdown.
- Return ONLY the SQL query.
"""

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=sql_prompt
        )

        sql_query = (
            response.text or ""
        ).strip()

        # Remove markdown
        sql_query = re.sub(
            r"```sql",
            "",
            sql_query,
            flags=re.IGNORECASE
        )

        sql_query = re.sub(
            r"```",
            "",
            sql_query
        ).strip()

        # -------------------------------------------------
        # SQL SAFETY
        # -------------------------------------------------

        sql_upper = sql_query.upper().strip()

        if not (
            sql_upper.startswith("SELECT")
            or sql_upper.startswith("WITH")
        ):

            st.error(
                "Only SELECT queries are allowed."
            )

            st.stop()

        forbidden_words = [
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "TRUNCATE",
            "CREATE",
            "REPLACE",
            "GRANT",
            "REVOKE"
        ]

        for word in forbidden_words:

            if re.search(
                rf"\b{word}\b",
                sql_upper
            ):

                st.error(
                    "Unsafe SQL query detected."
                )

                st.stop()

        # -------------------------------------------------
        # QUERY EXPLANATION
        # -------------------------------------------------

        explanation_prompt = f"""
Explain this SQL query in 2 short sentences.

Keep it simple and beginner-friendly.

SQL:
{sql_query}
"""

        explanation_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=explanation_prompt
        )

        explanation = (
            explanation_response.text or
            "This query retrieves data based on the user's question."
        ).strip()

        # =================================================
        # QUESTION DISPLAY
        # =================================================

        st.divider()

        st.subheader("❓ Your Question")

        st.info(question)

        # =================================================
        # SQL + EXPLANATION
        # =================================================

        col1, col2 = st.columns(2)

        with col1:

            st.subheader("🧾 Generated SQL Query")

            st.code(
                sql_query,
                language="sql"
            )

        with col2:

            st.subheader("📝 Query Explanation")

            st.info(
                explanation
            )

        # -------------------------------------------------
        # EXECUTE QUERY
        # -------------------------------------------------

        result_df = pd.read_sql(
            sql_query,
            engine
        )

        # -------------------------------------------------
        # EMPTY RESULT
        # -------------------------------------------------

        if result_df.empty:

            st.warning(
                "The query executed successfully, "
                "but no records were found."
            )

            st.stop()

        # =================================================
        # RESULT INFORMATION
        # =================================================

        st.subheader("📊 Query Result")

        r1, r2 = st.columns(2)

        with r1:

            st.metric(
                "Result Rows",
                len(result_df)
            )

        with r2:

            st.metric(
                "Result Columns",
                len(result_df.columns)
            )

        # =================================================
        # DOWNLOAD
        # =================================================

        csv_data = result_df.to_csv(
            index=False
        )

        st.download_button(
            "⬇️ Download Results as CSV",
            csv_data,
            "query_results.csv",
            "text/csv"
        )

        # =================================================
        # VISUALIZATION
        # =================================================

        st.subheader("📈 Data Visualization")

        if len(result_df.columns) >= 2:

            if chart_choice == "Automatic":

                chart_prompt = f"""
Choose the best visualization for this question.

Question:
{question}

Choose ONLY one:
bar
pie
line

Use:
bar for comparisons or rankings.
pie for proportions or shares.
line for trends over time.
"""

                chart_response = client.models.generate_content(
                    model=MODEL_NAME,
                    contents=chart_prompt
                )

                chart_type = (
                    chart_response.text or "bar"
                ).strip().lower()

                if chart_type not in [
                    "bar",
                    "pie",
                    "line"
                ]:

                    chart_type = "bar"

            else:

                chart_type = chart_choice.lower()

            x_column = result_df.columns[0]
            y_column = result_df.columns[1]

            # -------------------------------------------------
            # PIE
            # -------------------------------------------------

            if chart_type == "pie":

                fig = px.pie(
                    result_df,
                    names=x_column,
                    values=y_column,
                    title="Query Result"
                )

            # -------------------------------------------------
            # LINE
            # -------------------------------------------------

            elif chart_type == "line":

                fig = px.line(
                    result_df,
                    x=x_column,
                    y=y_column,
                    markers=True,
                    title="Query Result"
                )

            # -------------------------------------------------
            # BAR
            # -------------------------------------------------

            else:

                fig = px.bar(
                    result_df,
                    x=x_column,
                    y=y_column,
                    title="Query Result"
                )

            st.plotly_chart(
                fig,
                use_container_width=True
            )

        else:

            st.info(
                "At least two columns are required "
                "for visualization."
            )

        # =================================================
        # INSIGHTS
        # =================================================

        st.subheader("💡 Key Insights")

        result_sample = result_df.head(20).to_string(
            index=False
        )

        insight_prompt = f"""
You are a Data Analyst.

Analyze only this query result.

Question:
{question}

Result:
{result_sample}

Give 2 or 3 short factual insights.

Do not invent information.
Use only the provided result.
"""

        insight_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=insight_prompt
        )

        insights = (
            insight_response.text or
            "No additional insights available."
        ).strip()

        st.write(insights)

        # =================================================
        # QUERY HISTORY
        # =================================================

        st.session_state.history.append(
            {
                "question": question,
                "sql": sql_query
            }
        )

        # Keep last 20
        if len(st.session_state.history) > 20:

            st.session_state.history = (
                st.session_state.history[-20:]
            )

    except Exception as e:

        st.error(
            f"Something went wrong: {e}"
        )
        