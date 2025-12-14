-- Drop first (dev-friendly, avoids "CREATE IF NOT EXISTS" not altering schema)
DROP TABLE IF EXISTS invoice_line_items;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS clients;

CREATE TABLE clients (
  client_id VARCHAR(64) PRIMARY KEY,
  client_name VARCHAR(255) NOT NULL,
  industry VARCHAR(255),
  country VARCHAR(255)
);

CREATE TABLE invoices (
  invoice_id VARCHAR(64) PRIMARY KEY,
  client_id VARCHAR(64) NOT NULL,
  invoice_date DATE,
  due_date DATE,
  status VARCHAR(64),
  currency VARCHAR(16),
  fx_rate_to_usd DECIMAL(18, 6),
  CONSTRAINT fk_invoices_client
    FOREIGN KEY (client_id) REFERENCES clients(client_id)
);

CREATE TABLE invoice_line_items (
  line_id VARCHAR(64) PRIMARY KEY,
  invoice_id VARCHAR(64) NOT NULL,
  service_name VARCHAR(255),
  quantity DECIMAL(18, 4),
  unit_price DECIMAL(18, 4),
  tax_rate DECIMAL(18, 4),
  CONSTRAINT fk_items_invoice
    FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
);

CREATE INDEX idx_invoices_client_date ON invoices(client_id, invoice_date);
CREATE INDEX idx_clients_country ON clients(country);
CREATE INDEX idx_items_invoice ON invoice_line_items(invoice_id);
CREATE INDEX idx_items_service ON invoice_line_items(service_name);
