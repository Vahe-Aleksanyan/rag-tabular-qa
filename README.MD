# Task: Build a Chat Over Tabular Data (RAG-style)

You are given several Excel files that represent tables from a small business database:

- `Clients.xlsx` – information about clients
- `Invoices.xlsx` – invoices, dates, amounts, client IDs
- `InvoiceLineItems.xlsx` – line items for each invoice (service, quantity, rate, tax, etc.)

Your task is to build a question-answering chat that can answer natural-language questions about this data by:

1. Understanding the user's question.
2. Retrieving the relevant rows / records from the tables.
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
- Unfortunately we are not providing api key for the test task, but you can use https://console.groq.com/. There is a free plan and some models are available for API requests.
- The LLM should **not hallucinate numbers**; all numeric answers must come from actual data you've retrieved.

### Interface *(OPTIONAL)*

A simple interface is enough:

- CLI, Jupyter notebook, or a minimal web UI (e.g. Streamlit / Gradio ).

### Time Budget

Please spend no more than **8 hours** on this task.

If you don't fully complete all ideas, that's OK. Focus on building a clear, working core and documenting trade-offs.

## Deliverables

1. Code (repo) that can be run locally.

2. A short README describing:
   - How to run the project.
   - High-level architecture / design.
   - Assumptions and limitations.

3. Test Results Table with to columns in the root directory. Two columns:
    - Question
    - Answer provided by the pipeline 

## What We Will Look At

- How you structure the RAG pipeline (retrieval + generation).
- How you mitigate hallucinations / wrong numbers.
- Code clarity and organization.
- How you document assumptions and limitations.
