# Task: Build a Chat Over Tabular Data (RAG-style)

You are given several Excel files that represent tables from a small business database:

- `Clients.xlsx` – information about clients
- `Invoices.xlsx` – invoices, dates, amounts, client IDs
- `InvoiceLineItems.xlsx` – line items for each invoice (service, quantity, rate, tax, etc.)

Your task is to build a question-answering chat that can answer natural-language questions about this data by:

1. Understanding the user's question.
2. Retrieving the relevant rows/records from the tables.
3. Using an LLM to generate a grounded answer based on those records.

You may assume all data fits in memory (no need for complex scaling).

## Examples of Questions the Chat Should Handle

*(You don't have to hard-code exact answers, but your system should be able to answer questions of this type.)*

- List all clients with their industries.
- Which clients are based in the UK?
- List all invoices issued in March 2024 with their statuses.
- Which invoices are currently marked as "Overdue"?
- For each service_name in InvoiceLineItems, how many line items are there?
- List all invoices for Acme Corp with their invoice IDs, invoice dates, due dates, and statuses.
- Show all invoices issued to Bright Legal in February 2024, including their status and currency.
- For invoice I1001, list all line items with service name, quantity, unit price, tax rate, and compute the line total (including tax) for each.
- For each client, compute the total amount billed in 2024 (including tax) across all their invoices.
- Which client has the highest total billed amount in 2024, and what is that total?

*(Optional/extra questions)*
- Across all clients, which three services generated the most revenue in 2024? Show the total revenue per service.
- Which invoices are overdue as of 2024-12-31? List invoice ID, client name, invoice_date, due_date, and status.
- Group revenue by client country: for each country, compute the total billed amount in 2024 (including tax).
- For the service “Contract Review”, list all clients who purchased it and the total amount they paid for that service (including tax).
- Considering only European clients, what are the top 3 services by total revenue (including tax) in H2 2024 (2024-07-01 to 2024-12-31)?

## Requirements

### Architecture

Implement a RAG-style pipeline where:

1. The system maps the user's question to some structured retrieval/code over the tables
2. Retrieves relevant data (rows, aggregates, or both)
3. Feeds that context to an LLM to generate the final answer.

### LLM Usage

- You may use any LLM (open-source or API-based).
- Unfortunately, we are not providing api key for the test task, but you can use https://console.groq.com/. There is a free plan, and some models are available for API requests.
- The LLM should **not hallucinate numbers**; all numeric answers must come from actual data you've retrieved.

### Interface *(OPTIONAL)*

A simple interface is enough:

- CLI, Jupyter notebook, or a minimal web UI (e.g. Streamlit / Gradio ).

### Time Budget

Please spend no more than **5 hours** on this task.

If you don't fully complete all ideas, that's OK. Focus on building a clear, working core and documenting trade-offs.

## Deliverables

1. Create a fork of this repo and push your solution with all required artefacts. Send the link to your repo to our recruiter.

2. A short README describing:
   - How to run the project.
   - High-level architecture/design.
   - Assumptions and limitations.

3. Test Results Table with two columns in the root directory. Two columns:
    - Question from the list above
    - Answer (provided by the pipeline)

## What We Will Look At

- How do you structure the RAG pipeline (retrieval + generation)?
- How do you mitigate hallucinations / wrong numbers?
- Code clarity and organization.
- How do you document assumptions and limitations?



---

# Solution Implementation

The following sections describe the architecture, design decisions,
and evaluation of the implemented solution.

---

## Implementation Overview

This section describes the architecture, design decisions, and evaluation of the implemented solution.
The goal of the system is to answer natural-language questions over structured business data with a strong emphasis on **correctness, determinism, and safety**.

---

## Chat Over Tabular Data (RAG-Style)

This project implements a **chat-based question answering system over structured business data** (clients, invoices, invoice line items).

It follows a **RAG-style architecture**, where user questions are translated into SQL queries, executed against a relational database, and the retrieved results are used as grounded context for an LLM to generate the final answer.

The system prioritizes **numerical correctness and traceability** over fluent but potentially hallucinated responses.

---

## Data

The system operates over three relational tables ingested from Excel files:

* `clients` — client metadata (name, industry, country)
* `invoices` — invoice headers (dates, status, currency)
* `invoice_line_items` — services, quantities, prices, and tax rates

All data is stored in **MySQL**.

---

## High-Level Architecture

The pipeline is composed of the following stages:

### 1. Router (LLM with structured output)

* Interprets the user question.
* Chooses exactly one action:

  * `QUERY` → data can be retrieved
  * `CLARIFY` → required information is missing
  * `REFUSE` → question is out of scope
* Produces a strict JSON plan containing the intent and extracted fields.

### 2. Hybrid Retrieval Layer

* **Deterministic SQL** is used whenever the intent matches a predefined query.
* **Freeform SQL (LLM-generated)** is used only as a fallback when deterministic queries are insufficient.

### 3. SQL Safety Layer

* Enforces:

  * read-only `SELECT` queries
  * access to allowed tables only
  * automatic `LIMIT` for non-aggregate queries
* Prevents destructive or unsafe SQL execution.

### 4. Execution

* SQL is executed against MySQL.
* All queries are parameterized (no string interpolation).

### 5. Answer Synthesis (LLM)

* Generates a short natural-language answer.
* Uses **only the SQL result rows** as source of truth.
* Includes a numeric guard to prevent hallucinated values.
* Tables are rendered deterministically by the application, not the LLM.

### 6. User Interface

* Streamlit chat interface.
* Displays:

  * the answer
  * the result table
  * the executed SQL
  * the execution mode (deterministic vs freeform)

---

## Design Rationale

* **Correctness first**: all numbers originate from SQL results.
* **Determinism when possible**: predefined SQL for known intents.
* **Flexibility when needed**: controlled freeform SQL for complex analytics.
* **Safety by construction**: SQL validation before execution.
* **Explicit failure modes**: clarify or refuse instead of guessing.

---

## Project Structure (Simplified)

```
app/
  rag/            # routing, SQL generation, safety, answer synthesis
  db/             # MySQL engine, schema, ingestion
  llm/            # OpenAI client abstraction
  eval/           # evaluation logic and golden tests
  utils/          # logging and formatting helpers

services/
  api/            # FastAPI service
  ui/             # Streamlit UI

prompts/          # all LLM system prompts
data/             # Excel source files
```

---

## Logging

Structured logging is implemented across:

* routing decisions
* SQL generation and execution
* evaluation runs

All modules use a shared logging configuration for consistent output.

---

## Evaluation

Two complementary evaluation approaches are implemented.

### 1. Test Results Table (Task Requirement)

* Runs a fixed list of questions.
* Produces a **two-column table**:

  * Question
  * Answer (generated by the full pipeline)

Generated per model:

```
Test_Results_Table.<model>.md
```

### 2. Golden Evaluation (Correctness)

* Uses a YAML-defined golden dataset.
* Validates:

  * routing action and intent
  * extracted fields
  * SQL result equivalence against oracle SQL
* No LLM judgment is used for correctness.

Generated per model:

```
Eval_Report.<model>.md
```

This enables **direct comparison between models** (e.g. GPT-5.2 vs GPT-4o-mini).

---

## How to Run the Project

### Prerequisites

* Docker and Docker Compose
* Python 3.12+
* OpenAI API key

Set the API key:

```bash
export OPENAI_API_KEY=your_key_here
```

---

### 1. Start the Database

```bash
docker compose up -d db
```

---

### 2. Ingest Excel Data

```bash
docker compose run --rm api python -m app.db.ingest_excel
```

Expected output:

```
Inserted: clients=20, invoices=40, items=96
```

---

### 3. Start API and UI

```bash
docker compose up
```

* API: [http://localhost:8000](http://localhost:8000)
* UI:  [http://localhost:8501](http://localhost:8501)

---

## Running Evaluations

Evaluations are executed **locally using the Python virtual environment**, while the database runs in Docker.

### 1. Activate the virtual environment

```bash
source .venv/bin/activate
```

### 2. Ensure the database is running

```bash
docker compose up -d db
```

### 3. Generate test-results tables

```bash
OPENAI_MODEL=gpt-5.2 python -m app.eval.run_eval
OPENAI_MODEL=gpt-4o-mini python -m app.eval.run_eval
```

### 4. Run golden correctness evaluation

```bash
OPENAI_MODEL=gpt-5.2 python -m app.eval.check_golden
OPENAI_MODEL=gpt-4o-mini python -m app.eval.check_golden
```


## Assumptions and Limitations

* The dataset is assumed to **fit in memory** and is queried from a single MySQL instance (no sharding or distributed execution).
* The schema is assumed to be **stable and known in advance**; schema discovery and evolution are out of scope.
* Currency conversion is performed **only when explicitly requested** and relies on the stored `fx_rate_to_usd` values.
* Freeform SQL generation is intentionally **restricted and validated** to ensure safety and correctness; not all arbitrary SQL queries are supported.
* The system prioritizes **deterministic retrieval and numerical correctness** over conversational flexibility.
* Evaluation focuses on **routing correctness and SQL result equivalence** rather than subjective answer quality.

---
