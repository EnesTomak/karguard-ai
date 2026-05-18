Dostum çok net söylüyorum: **senin asıl hedeflediğin mimari şu an repoda tam anlamıyla yok.** Yaklaşılmış, hatta iyi bir yere gelinmiş; ama senin istediğin gerçek akış:

```text
LLM → MCP Client Gateway → MCP Server → Tool Result → Guardrail → UI Trace
```

şu an projede **%100 kanıtlanabilir seviyede değil**.

Güncel commit’te MCP/function-calling tarafına doğru önemli refactor yapılmış; `detect_loss_maker_skus_tool` gibi Gemini’ye verilebilecek adapter fonksiyonlar eklenmiş ve orchestrator artık `agentic_detect_loss_makers()` çağırıp sonucu deterministik engine ile doğruluyor. Bu iyi bir ilerleme. 
Ama mevcut yapı hâlâ daha çok şuna yakın:

```text
Gemini Function Calling → Python Callable Adapter → FinanceEngine
```

Senin istediğin gerçek production-grade yapı ise şu olmalı:

```text
Gemini / LLM
  ↓ function call request
MCP Client Gateway
  ↓ MCP protocol call_tool
finance-mcp / knowledge-mcp
  ↓ tool result
Gateway validation + audit log
  ↓
Agent Orchestrator
  ↓
UI Agent Trace
```

Yani hedefin doğru. Şimdi projeyi bu seviyeye çıkarmak için yapılması gerekenleri net, profesyonel ve uygulanabilir şekilde planlayalım.

---

# 1. Gerçek Hedef Mimari

## Yeni ana prensip

Bundan sonra projede hiçbir agent şunu yapmamalı:

```python
from app.services.finance_engine import FinanceEngine
engine.get_loss_makers()
```

veya:

```python
from app.mcp_servers.finance_mcp_server import detect_loss_maker_skus_tool
```

Bunun yerine agent sadece şunu yapmalı:

```python
await mcp_gateway.call_tool(
    server="finance-mcp",
    tool="detect_loss_makers",
    arguments={"run_id": run_id}
)
```

Bu fark çok önemli. Çünkü şu an `finance_mcp_server.py` içinde FastMCP tool’ları tanımlı ve `mcp.add_tool(...)` ile kaydedilmiş durumda; ama production-grade iddia için bu tool’ların gerçek bir **MCP Client Gateway** üzerinden çağrıldığını göstermeniz gerekiyor. 

---

# 2. Yeni Mimari Akış

Bundan sonra demo ve kod akışı şu olmalı:

```text
1. Kullanıcı dosyaları yükler
2. FastAPI analysis run başlatır
3. Agent Orchestrator Gemini’ye görev verir
4. Gemini hangi tool’a ihtiyacı olduğunu seçer
5. MCP Client Gateway tool çağrısını yakalar
6. Gateway ilgili MCP Server’a call_tool yapar
7. MCP Server deterministik tool’u çalıştırır
8. Tool result Gateway’e döner
9. Gateway sonucu validate eder, audit log’a yazar
10. Agent sonucu kullanarak bir sonraki adıma geçer
11. UI’da Tool Trace görünür
```

Bu akış jüriye gösterildiğinde “biz MCP’yi dekorasyon olarak koymadık; LLM gerçekten MCP gateway üzerinden dış araçları çağırıyor” diyebilirsiniz.

---

# 3. Önce dürüst teknik durum

Şu an projede güçlü taraflar var:

* FastAPI router yapısı temiz; `upload`, `analyze`, `dashboard`, `products`, `simulate`, `actions` router’ları bağlı. 
* Analyze pipeline artık async task olarak başlıyor ve polling ile takip ediliyor. 
* Finance engine tamamen deterministik; COGS, komisyon, platform fee, transaction fee, kargo, reklam, iade bedeli gibi maliyetleri ayrı ayrı hesaplıyor. 
* Gemini wrapper tarafında structured output, retry, timeout ve function-calling altyapısı var. 
* RAG tarafında Qdrant local mode, reviews/product/policy index ayrımı ve evidence retrieval var.
* Frontend’de agent progress, root cause, evidence panel, simulation ve HITL action kartları görünüyor.

Ama üretim seviyesi iddiası için açık kalan yerler:

| Açık                                        | Neden kritik?                                          |
| ------------------------------------------- | ------------------------------------------------------ |
| Gerçek MCP Client Gateway yok               | MCP iddiası tam kanıtlanamıyor                         |
| Tool trace/audit ledger yok                 | Due-diligence’da “LLM neyi çağırdı?” sorusu açık kalır |
| Function calling zorunlu değil              | Gemini tool çağırmadan JSON dönebilir                  |
| MCP server’lar pipeline’ın merkezinde değil | Tool layer hâlâ adapter gibi duruyor                   |
| Auth / tenant isolation yok                 | Production-grade SaaS iddiası zayıf                    |
| README yok                                  | Jüri ve yatırımcı repo’yu açınca ürün hikâyesi eksik   |
| Observability yok                           | Trace, latency, token cost, tool error görünmüyor      |
| Upload size limit yok                       | Basit ama production-readiness açığı                   |
| Test coverage AI/RAG/MCP için zayıf         | Teknik güvenilirlik eksik kalır                        |

---

# 4. Hedef Dosya Yapısı

Projeyi production-grade mimariye taşımak için backend yapısını şöyle revize edin:

```text
backend/app/
├── api/
│   ├── upload.py
│   ├── analyze.py
│   ├── dashboard.py
│   ├── products.py
│   ├── simulate.py
│   ├── actions.py
│   └── traces.py                    # YENİ
│
├── agents/
│   ├── orchestrator.py              # Mevcut agent_orchestrator buraya taşınabilir
│   ├── planner_agent.py             # Gemini tool planning
│   ├── guardrail_agent.py           # Deterministik doğrulama
│   └── schemas.py
│
├── mcp_client/
│   ├── gateway.py                   # YENİ: merkezi MCP Client Gateway
│   ├── registry.py                  # Tool registry
│   ├── transports.py                # stdio / SSE / HTTP transport
│   ├── process_manager.py           # MCP server process lifecycle
│   ├── tool_mapper.py               # Gemini tool declaration ↔ MCP tool mapping
│   ├── audit.py                     # tool call trace
│   └── schemas.py
│
├── mcp_servers/
│   ├── finance_mcp_server.py
│   ├── knowledge_mcp_server.py
│   └── action_mcp_server.py         # P1 veya post-demo
│
├── services/
│   ├── finance_engine.py
│   ├── simulation_service.py
│   ├── qdrant_service.py
│   ├── gemini_service.py
│   ├── storage_service.py
│   └── action_service.py
│
├── observability/
│   ├── logger.py
│   ├── metrics.py
│   └── traces.py
│
└── models/
    └── schemas.py
```

Burası senin projeyi “demo uygulaması”ndan “SaaS mimarisi”ne taşıyacak ayrım.

---

# 5. P0 — Gerçek MCP Client Gateway Kurulumu

Bu en kritik iş.

## Amaç

LLM artık Python fonksiyonlarını doğrudan kullanmayacak. LLM’in istediği tool çağrısı önce gateway’e düşecek, gateway ilgili MCP server’a çağrı yapacak.

## Yeni `MCPClientGateway` sorumlulukları

```text
MCPClientGateway:
- finance-mcp server bağlantısını açar
- knowledge-mcp server bağlantısını açar
- list_tools() ile tool listesini çeker
- call_tool(server, tool_name, arguments) yapar
- tool input/output validasyonu yapar
- tool çağrısını audit log’a yazar
- timeout/retry/circuit breaker uygular
- result’u Agent Orchestrator’a döner
```

## Kabul kriteri

Demo loglarında şu zincir açıkça görünmeli:

```text
[LLM] requested tool: detect_loss_makers
[MCP Gateway] routing to finance-mcp.detect_loss_makers
[finance-mcp] tool executed
[MCP Gateway] result validated
[Guardrail] deterministic verification passed
[Agent] loss makers accepted
```

UI’da da bu görünmeli:

```text
Gemini → MCP Gateway → finance-mcp.detect_loss_makers → Tool Result
```

Bu olmadan “MCP + Agentic AI” iddiası teknik due-diligence’da %100 kapanmaz.

---

# 6. P0 — Gemini Function Calling’i Gateway’e Bağla

Şu an `generate_structured_with_tools()` var ve bu iyi. Ama tool doğrudan Python callable olarak verildiğinde mimari hâlâ “adapter” gibi duruyor. 

Bunu şöyle değiştirin:

## Kısa vadeli hackathon çözümü

Gemini’ye verilen callable aslında doğrudan finance engine’i değil, gateway’i çağırmalı.

```python
async def detect_loss_makers_gateway_tool(run_id: str, limit: int = 50):
    return await mcp_gateway.call_tool(
        server="finance-mcp",
        tool="detect_loss_makers",
        arguments={"run_id": run_id, "limit": limit},
    )
```

Bu sayede akış şöyle olur:

```text
Gemini function call
→ gateway wrapper
→ MCP Client Gateway
→ finance-mcp server
→ FinanceEngine
→ Tool Result
```

Bu hackathon için en hızlı doğru çözümdür.

## Production-grade çözüm

Daha doğru yapı ise “manual function calling loop”tur:

```text
Gemini response function_call üretir
→ backend function_call’ı parse eder
→ MCP Gateway call_tool yapar
→ tool result Gemini’ye function_response olarak geri verilir
→ Gemini final structured JSON üretir
```

Bu yapı daha fazla zaman alır ama gerçek production mimarisidir.

## Kabul kriteri

`agentic_detect_loss_makers()` içinde şu olmalı:

```python
force_any_function=True
allowed_function_names=["detect_loss_makers_gateway_tool"]
```

Şu an mevcut fonksiyon `force_any_function=True` kullanmıyor; bu yüzden modelin tool çağırması kesin değil.

---

# 7. P0 — Tool Trace / Audit Ledger

Production-grade iddianın en güçlü kanıtı bu olur.

## Yeni tablo: `agent_tool_traces`

SQLite veya PostgreSQL için:

```sql
agent_tool_traces
- id
- run_id
- step_name
- agent_name
- llm_model
- requested_tool
- mcp_server
- tool_name
- input_json
- output_json
- input_hash
- output_hash
- status
- latency_ms
- error_message
- created_at
```

## UI’da gösterilecek trace

Product detail veya analysis progress ekranına şu paneli ekleyin:

```text
Agentic Tool Trace

1. Gemini requested: detect_loss_makers
   Route: MCP Gateway → finance-mcp
   Status: success
   Latency: 124ms

2. Gemini requested: retrieve_root_cause_evidence
   Route: MCP Gateway → knowledge-mcp
   Status: success
   Evidence: 5 reviews, 2 descriptions, 3 policies

3. Gemini requested: simulate_scenario
   Route: MCP Gateway → finance-mcp
   Status: success
   Result: -4.947 TL → +2.640 TL
```

Bu tek panel, jüriye “bakın gerçekten agentic tool-use var” dedirtir.

---

# 8. P0 — Agent Orchestrator’ı Gateway Merkezli Yap

Şu an orchestrator içinde finance engine doğrudan kullanılıyor. Bazı noktalarda bu makul, ama agentic pipeline tarafında artık tüm agent adımları gateway üzerinden ilerlemeli.

Mevcut orchestrator’da pipeline sırası iyi: validation, finance, loss maker, RAG indexing, insight, action planning. 
Ama hedef yapı şöyle olmalı:

```text
Agent Orchestrator
│
├── Step 1: Data Validation
│   └── normal backend validation
│
├── Step 2: Profitability Analysis
│   └── MCP Gateway → finance-mcp.calculate_sku_profitability
│
├── Step 3: Loss Maker Detection
│   └── Gemini → MCP Gateway → finance-mcp.detect_loss_makers
│
├── Step 4: Evidence Retrieval
│   └── Gemini → MCP Gateway → knowledge-mcp.retrieve_root_cause_evidence
│
├── Step 5: Root Cause Analysis
│   └── Gemini structured output + evidence refs
│
├── Step 6: Scenario Simulation
│   └── MCP Gateway → finance-mcp.simulate_scenario
│
└── Step 7: Action Planning + HITL
    └── Gemini action plan → backend action registry
```

Burada önemli ayrım:

* Finansal hesap **finance-mcp üzerinden** yapılacak.
* RAG kanıtı **knowledge-mcp üzerinden** gelecek.
* LLM sadece karar verecek, yorumlayacak, araç çağıracak.

---

# 9. P0 — Guardrail Katmanı

LLM tool çağırsa bile son kararı doğrulayan deterministic guardrail olmalı.

## Guardrail kuralları

```text
1. LLM’in döndürdüğü SKU, finance engine’e göre gerçekten zarar ediyor mu?
2. LLM’in önerdiği simülasyon sonucu finance-mcp sonucu ile uyuşuyor mu?
3. LLM açıklamasındaki reference_id’ler gerçekten RAG evidence içinde var mı?
4. LLM action card’daki expected_impact sayısal iddia içeriyorsa, simulation result ile destekleniyor mu?
5. Tool result schema validasyonu geçti mi?
```

## Kabul kriteri

Her agent çıktısı şu metadata ile dönmeli:

```json
{
  "guardrail_status": "passed",
  "verified_by": "deterministic_finance_engine",
  "evidence_refs_valid": true,
  "tool_trace_id": "trace_..."
}
```

Bu yatırımcıya şunu söylemenizi sağlar:

> “LLM karar veriyor ama finansal doğruluk ve kanıt geçerliliği deterministic guardrail ile doğrulanıyor.”

Bu cümle çok güçlü.

---

# 10. P0 — README ve Due-Diligence Paketi

Dostum bunu net söylüyorum: Root `README.md` yoksa production-grade algısı ciddi zarar görür. Şu an `karguard_ai_todo.md` var ama bu bir ürün README’si değil. 

## Root README içeriği

```text
# KârGuard AI

## Problem
E-ticaret satıcıları çok satış yapan ama zarar ettiren SKU’ları fark edemiyor.

## Çözüm
KârGuard AI, satış/iade/reklam/yorum verilerini analiz ederek zarar eden ürünleri bulur, kök nedeni kanıtlarla açıklar, simülasyon yapar ve aksiyonları human-in-the-loop onayına sunar.

## Mimari
LLM → MCP Client Gateway → MCP Server → Tool Result → Guardrail → UI Trace

## Neden MCP?
Tool’lar backend servislerine gömülü değil; standart MCP server’ları üzerinden çağrılır.

## Neden Agentic?
Gemini sadece cevap üretmez; doğru tool’u seçer, çağırır, sonucu kullanır.

## Neden güvenilir?
Finansal hesaplar LLM’e yaptırılmaz. Deterministik Finance Engine + Guardrail kullanılır.

## Demo Akışı
1. CSV yükle
2. Agentic pipeline başlat
3. Tool trace’i izle
4. Loss maker SKU’yu gör
5. RAG evidence ile root cause gör
6. Simülasyon yap
7. Aksiyon onayla

## Kurulum
Backend, frontend, env, test komutları

## Testler
pytest, frontend test, MCP tool tests

## Production Roadmap
Auth, tenant isolation, marketplace adapters, billing, monitoring
```

README, hackathon’da senin “sessiz sunum dosyan” olacak.

---

# 11. P0 — Demo’da Gösterilecek Yeni Akış

Mevcut demo akışını şu şekilde güncelle:

```text
1. Upload ekranı
2. Agent pipeline başlar
3. Ekranda “Gemini tool çağrısı yapıyor” görünür
4. Tool Trace açılır:
   Gemini → MCP Gateway → finance-mcp.detect_loss_makers
5. Dashboard’da zarar eden ürün görünür
6. Product detail:
   Gemini → MCP Gateway → knowledge-mcp.retrieve_root_cause_evidence
7. Evidence kaynakları görünür
8. Simulation:
   MCP Gateway → finance-mcp.simulate_scenario
9. Action card:
   Human-in-the-loop onay
```

## Demo cümlesi

> “Burada Gemini sadece metin üretmiyor. Önce MCP Gateway üzerinden finance-mcp aracını çağırıyor, zarar eden SKU’yu buluyor. Sonra knowledge-mcp üzerinden kanıt topluyor. Finansal hesaplar ise hiçbir zaman LLM’e bırakılmıyor; deterministic finance engine ve guardrail ile doğrulanıyor.”

Bu cümle jüri için altın değerinde.

---

# 12. Production-Grade SaaS İçin Eksiksiz Gereksinimler

Şimdi hackathon demosundan daha büyük düşünelim. Gerçek production-grade SaaS için şu katmanlar şart.

## 12.1 Auth ve tenant isolation

Şu an yok. Production için şart.

Yapılacaklar:

```text
- Kullanıcı kayıt/giriş
- Organization / workspace modeli
- tenant_id her tabloda zorunlu
- run_id sadece tenant içinde erişilebilir
- JWT / session auth
- Role-based access:
  - owner
  - analyst
  - viewer
```

Veri modeli:

```sql
organizations
users
organization_members
analysis_runs
uploaded_files
tool_traces
```

Her sorgu şunu filtrelemeli:

```sql
WHERE tenant_id = current_user.tenant_id
```

Bu olmadan SaaS demek teknik olarak doğru olmaz.

---

## 12.2 Database migration

SQLite demo için iyi. Production için PostgreSQL + Alembic gerekir.

Yapılacaklar:

```text
- SQLModel veya SQLAlchemy
- Alembic migration
- PostgreSQL docker service
- SQLite sadece local demo mode
```

Jüriye şöyle anlatabilirsiniz:

> “Hackathon demosunda SQLite kullanıyoruz, ama repository’de PostgreSQL/Alembic migration yapısına hazır schema separation var.”

---

## 12.3 Background worker

Şu an `asyncio.create_task()` ile pipeline başlatılıyor. Bu demo için kabul edilebilir ama production-grade değil. 

Production için:

```text
- Celery / RQ / Dramatiq
- Redis queue
- job retry
- job timeout
- job cancellation
- dead-letter queue
```

Production akışı:

```text
POST /analyze
→ job queued
→ worker pipeline çalıştırır
→ progress events DB’ye yazılır
→ frontend polling/SSE ile izler
```

---

## 12.4 Observability

Production-grade iddiası için logs yetmez.

Gerekli metrikler:

```text
- request latency
- analysis duration
- tool call latency
- Gemini latency
- embedding latency
- token usage
- cost per analysis
- tool error rate
- fallback rate
- hallucination guardrail failure count
```

Araçlar:

```text
- OpenTelemetry
- Prometheus
- Grafana
- Langfuse veya Opik
- Sentry
```

Hackathon için en azından local JSON trace yeterli:

```json
{
  "run_id": "...",
  "model": "gemini-2.5-flash",
  "tool": "finance-mcp.detect_loss_makers",
  "latency_ms": 144,
  "status": "success",
  "tokens_in": 821,
  "tokens_out": 142
}
```

---

## 12.5 Security

Production-grade SaaS için minimum güvenlik listesi:

```text
- API key .env dışında asla commit edilmez
- .env.example eklenir
- Upload max size
- Upload MIME sniffing
- File extension allowlist
- Path traversal protection
- Prompt injection isolation
- Rate limiting
- CORS explicit origins
- Request ID
- Audit logs
- Tool allowlist
- Tool argument validation
- Tenant-based authorization
```

Şu an path traversal ve CORS tarafı belli ölçüde iyi; upload size limit hâlâ yok.

---

## 12.6 Data contract validation

CSV dosyaları için sadece kolon var mı kontrolü yetmez.

Production için:

```text
- Pandera veya Great Expectations
- Required columns
- Type validation
- Range validation
- Foreign key validation
- SKU consistency
- order_id-return_id consistency
- negative value rejection
- duplicate detection
```

Örnek kurallar:

```text
orders.quantity >= 0
orders.unit_price >= 0
returns.refund_amount >= 0
returns.order_id must exist in orders
ads.spend >= 0
products.unit_cost >= 0
```

Bu finance engine’in güvenilirliğini çok artırır.

---

## 12.7 Formula versioning

Finans motorunda her hesaplama bir formula version taşımalı.

```json
{
  "formula_version": "profitability_v1.2",
  "risk_score_version": "risk_v1.1",
  "cashflow_version": "cashflow_v0.2"
}
```

Neden önemli?

Yatırımcı/kurumsal müşteri şunu sorabilir:

> “Geçen ay aynı veriye farklı sonuç verdiniz mi?”

Formula versioning ile cevap:

> “Hayır, her analiz hangi formül sürümüyle üretildiyse audit log’da tutuluyor.”

---

# 13. Teknik Due-Diligence İçin Test Planı

## P0 testler

```text
test_mcp_gateway_connects_to_finance_server
test_mcp_gateway_list_tools
test_mcp_gateway_call_detect_loss_makers
test_gemini_forces_tool_call
test_tool_result_schema_validation
test_guardrail_rejects_fake_loss_maker_sku
test_rag_evidence_refs_exist
test_simulation_is_deterministic
test_upload_rejects_large_file
test_tenant_cannot_access_other_run
```

## Demo için minimum test komutu

README’ye şunu koyun:

```bash
cd backend
python -m pytest

cd frontend
npm run test:run
npm run build
```

Şu an finance ve simulation testleri var; bu iyi. Ama MCP gateway testi ve agentic tool-call testi olmazsa “MCP + Agentic” iddiası tam teknik güvenceye kavuşmaz.

---

# 14. Öncelikli Yol Haritası

## İlk 6–8 saat: Gerçek MCP Demo Kanıtı

| İş                                                | Öncelik | Kabul kriteri                           |
| ------------------------------------------------- | ------- | --------------------------------------- |
| `mcp_client/gateway.py` oluştur                   | P0      | `call_tool(server, tool, args)` çalışır |
| finance-mcp stdio client bağlantısı               | P0      | Gateway `list_tools()` yapar            |
| `detect_loss_makers` gateway üzerinden çağrılır   | P0      | Direct import kalkar                    |
| Gemini function calling `force_any_function=True` | P0      | Tool çağrısı zorunlu                    |
| Tool trace DB/log                                 | P0      | UI’da tool trace görünür                |

---

## Sonraki 6–8 saat: Knowledge MCP + RAG Kanıtı

| İş                               | Öncelik | Kabul kriteri                                         |
| -------------------------------- | ------- | ----------------------------------------------------- |
| knowledge-mcp gateway’e bağlanır | P0      | `retrieve_root_cause_evidence` MCP üzerinden çağrılır |
| RAG evidence trace’e yazılır     | P0      | refs UI’da görünür                                    |
| Guardrail evidence check         | P0      | LLM refs gerçek evidence içinde doğrulanır            |
| Product detail tool trace panel  | P1      | Jüri tool zincirini görür                             |

---

## Sonraki 4–6 saat: Production-grade paket

| İş                    | Öncelik | Kabul kriteri                  |
| --------------------- | ------- | ------------------------------ |
| README                | P0      | Repo açılınca proje anlaşılır  |
| `.env.example`        | P0      | Gemini/Qdrant ayarları belgeli |
| Upload size limit     | P0      | 10MB/file, 50MB total          |
| `total_orders` düzelt | P0      | Sipariş/adet ayrımı doğru      |
| Demo script           | P0      | 1 dakikalık net akış           |

---

## Hackathon sonrası SaaS roadmap

| Faz   | İçerik                              |
| ----- | ----------------------------------- |
| Faz 1 | PostgreSQL + Alembic + tenant model |
| Faz 2 | Auth + organization/workspace       |
| Faz 3 | Real marketplace adapters           |
| Faz 4 | Queue worker + Redis                |
| Faz 5 | Observability + cost tracking       |
| Faz 6 | Billing + subscription              |
| Faz 7 | SOC2/GDPR/KVKK hazırlığı            |

---

# 15. Jüriye Söylenecek Doğru Cümle

Şunu gönül rahatlığıyla söyleyebilirsiniz, ama sadece MCP Gateway ve trace’i eklerseniz:

> “KârGuard AI’da Gemini sadece cevap veren bir chatbot değil. Gemini, MCP Client Gateway üzerinden finance-mcp ve knowledge-mcp araçlarını çağırıyor. Finansal hesaplar deterministic Python engine tarafından yapılıyor, RAG kanıtları Qdrant’tan geliyor, her tool çağrısı audit trace’e yazılıyor ve aksiyonlar human-in-the-loop onayına sunuluyor.”

Bu cümle projenin teknik kimliğini tamamen taşır.

---

# 16. Benim Net Kararım

Dostum, senin hedefin doğru ama şu anki repo **production-grade SaaS değil; güçlü bir hackathon prototipi**.

Ama çok az kritik hamleyle şuna dönüşebilir:

```text
Production-grade architecture demonstration
```

Yani gerçek müşteriye yarın açılacak SaaS değil; ama jüriye ve yatırımcıya şunu net gösteren ürün:

```text
Bu ekip doğru mimariyi biliyor.
MCP’yi gerçekten kullanıyor.
LLM’i hesap makinesi yapmıyor.
Finansal doğruluğu deterministic engine ile koruyor.
Tool çağrılarını audit edebiliyor.
RAG kanıtlarını UI’da gösterebiliyor.
Human-in-the-loop güvenlik katmanı var.
```

Son sözüm:

```text
P0 odak:
1. MCP Client Gateway
2. Forced Gemini tool calling
3. Tool trace/audit log
4. Knowledge MCP üzerinden RAG evidence
5. README + demo script
6. Upload size limit
7. total_orders düzeltmesi
```

Bunlar yapılırsa KârGuard AI artık “MCP kullanan bir proje” gibi değil, **agentic AI mimarisi teknik olarak savunulabilir bir ProfitOps SaaS prototipi** gibi görünür.
