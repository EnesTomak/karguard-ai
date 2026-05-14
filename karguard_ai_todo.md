# KârGuard AI - Proje Durum Raporu ve TODO

> Son güncelleme: **14 Mayıs 2026**
>  
> Bu dosya, mevcut repo durumu (`backend/` + `frontend/`) taranarak güncellenmiştir.

---

## Genel Durum Özeti

- Frontend: **Çalışıyor**
- Backend API: **Çalışıyor**
- AI (Gemini): **Çalışıyor**
- RAG (Qdrant): **Çalışıyor**
- MCP Katmanı: **Çalışıyor**
- SQLite kalıcılık: **Çalışıyor**
- Test altyapısı: **Kuruldu ve çalıştırıldı**

Tahmini tamamlanma: **%92**

---

## Yapılanlar

### 1) Proje Altyapısı
- [x] Backend ve frontend dizin yapısı oluşturuldu
- [x] `requirements.txt` ve frontend bağımlılıkları tanımlandı
- [x] Ortam değişkenleri üzerinden konfigürasyon yapısı kuruldu (`config.py`)

### 2) FastAPI Backend (Katman 2)
- [x] Ana uygulama ve router kayıtları (`upload`, `analyze`, `dashboard`, `products`, `simulate`, `actions`)
- [x] Upload endpointi (CSV/XLSX/MD/TXT doğrulama ve kayıt)
- [x] Analyze pipeline endpointi
- [x] Dashboard / Product / Simulation / Actions endpointleri

### 3) Deterministic Finance Engine (Katman 4)
- [x] SKU profitability hesaplamaları
- [x] Risk score hesaplaması
- [x] 14 günlük cashflow tahmini
- [x] Dashboard KPI hesaplamaları

### 4) Scenario Simulator
- [x] Fiyat değişikliği simülasyonu
- [x] Reklam bütçesi değişikliği simülasyonu
- [x] İade oranı değişikliği simülasyonu
- [x] Talep değişimi simülasyonu

### 5) Agent Orchestrator
- [x] Data validation adımı
- [x] Profitability adımı
- [x] Loss-maker tespiti
- [x] RAG indexing adımı
- [x] Insight (kök neden) adımı
- [x] Action planning adımı

### 6) AI Katmanı (Gemini) - Katman 3
- [x] Gemini client servisi
- [x] Structured JSON output
- [x] Insight agent kök neden analizi
- [x] Action planning agent
- [x] MCP function-calling entegrasyonu (`generate_text_with_tools`)

### 7) RAG / Knowledge Layer (Qdrant) - Katman 6
- [x] Qdrant health check
- [x] `gemini-embedding-2` embedding pipeline
- [x] `reviews_index` indeksleme
- [x] `product_description_index` indeksleme
- [x] `policy_index` indeksleme
- [x] Semantic search fonksiyonları
  - [x] `search_reviews_by_sku`
  - [x] `search_product_description`
  - [x] `retrieve_root_cause_evidence`
  - [x] `search_marketplace_policy`
  - [x] `generate_evidence_summary`

### 8) MCP Tool Katmanı - Katman 5
- [x] Finance MCP server araçları
  - [x] `calculate_sku_profitability`
  - [x] `detect_loss_makers`
  - [x] `simulate_scenario`
  - [x] `forecast_cashflow_14d`
  - [x] `calculate_risk_score`
- [x] Knowledge MCP server araçları
  - [x] `search_reviews_by_sku`
  - [x] `search_product_description`
  - [x] `retrieve_root_cause_evidence`
  - [x] `search_marketplace_policy`
  - [x] `generate_evidence_summary`
- [x] MCP <-> Gemini function-calling bağlantısı

### 9) Veri Katmanı (Katman 7)
- [x] Mock CSV setleri (`orders`, `returns`, `products`, `ads`, `reviews`)
- [x] `product_descriptions.csv`
- [x] `marketplace_policy.md`
- [x] `brand_voice.md`

### 10) Veritabanı (SQLite / Local Storage)
- [x] SQLite entegrasyonu (`karguard.db`)
- [x] Analiz run geçmişi tablosu
- [x] KPI snapshot tablosu
- [x] Ürün snapshot tablosu
- [x] Root-cause snapshot tablosu
- [x] Aksiyon kartları tablosu
- [x] API tarafında memory + SQLite fallback/hybrid okuma-yazma

### 11) Frontend (Katman 1)
- [x] Upload sayfası
- [x] Dashboard sayfası
- [x] Product detail + root cause + simulation + action kartları
- [x] API entegrasyonu
- [x] Responsive arayüz

### 12) Kod Kalitesi ve Test (H)
- [x] Backend unit testleri (`finance_engine`, `simulation`)
- [x] API endpoint testleri (`pytest + httpx`)
- [x] Frontend component testleri (Vitest + Testing Library)
- [x] Error handling iyileştirmeleri (global exception handlers)
- [x] Logging sistemi (request log + request id + startup log)

---

## Yapılacaklar (Kalan İşler)

### Kritik / Önemli
- [x] Action kartları için **düzenle (edit)** akışının tamamlanması

### Demo / Ürünleştirme
- [ ] Demo videosu kaydı
- [ ] README / kullanım dokümantasyonunun genişletilmesi (kurulum, test, örnek akış)

### Teknik İyileştirme (Opsiyonel ama değerli)
- [ ] Frontend bundle boyutu optimizasyonu (code-splitting / lazy loading)
- [ ] FastAPI `on_event` yerine lifespan geçişi (deprecation cleanup)
- [ ] Test kapsamının artırılması (edge-case ve entegrasyon seviyesinde)

---

## Hızlı Doğrulama Komutları

### Backend
- `cd backend`
- `.venv\Scripts\python -m pytest`

### Frontend
- `cd frontend`
- `npm run test:run`
- `npm run build`
