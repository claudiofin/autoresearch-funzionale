# Project Context
Generated: 2026-04-23 13:34:51

This file contains the extracted context from all input files (notes, PDF, DOCX, screenshots, HTML).
It serves as the "Bible" for the functional analysis agents.

---

## 1. Regole di Business (Estratte dalle note)

### [TEXT] note.txt
```
# VetUnitaApp - Analisi Funzionale e Pivot Strategico

> Documento di analisi dello stato attuale dell'app e proposta di evoluzione con focus su benchmarking, clustering e confronto prezzi tra cliniche veterinarie.

---

## 📊 1. ANALISI FUNZIONALE ATTUALE

### 1.1 Architettura Tecnica

| Componente | Tecnologia | Descrizione |
|------------|-----------|-------------|
| Frontend | React Native + Expo Router | App mobile cross-platform (iOS/Android) |
| Backend | Convex | Database real-time con funzioni serverless |
| State Management | Zustand | Store locale per auth e onboarding |
| UI | Custom Components + Reanimated | Animazioni fluide e skeleton loading |

### 1.2 Struttura Tab Principali

#### 🏠 Dashboard (Hub Clinico)
**Funzionalità attuali:**
- Visualizzazione risparmio totale YTD con indicatore percentuale (+14.2%)
- Top distributori con barre di progresso (Zoetis 45%, MSD 30%, Henry Schein 15%)
- Lista acquisti recenti con badge di stato ("Riordinato")
- Pull-to-refresh per aggiornare i dati
- Skeleton shimmer per loading state

**Dati visualizzati:**
- RISPARMIO TOTALE YTD: $42,850
- Distributori principali con percentuali
- Acquisti recenti: Bravecto ($840), Nobivac ($1,250), Forniture Miste ($320)

#### 📖 Catalogo
**Funzionalità attuali:**
- Ricerca farmaci per nome/principio attivo
- Filtri rapidi per categoria (Antibiotici, Antiparassitari, FANS, Integratori)
- Card prodotto principale con badge sconto Network (-20%)
- Alternativa intelligente con confronto prezzi
- Features: bioequivalenza certificata, spedizione gratuita, disponibilità network

**Dati visualizzati:**
- AmoxiClav Premium: $99.20 (era $124.00)
- Alternativa: MeloFlex Generic a $46.75 (risparmio 45%)

#### 🏷️ Offerte
**Funzionalità attuali:**
- Top deal card con countdown timer (es. "Top Deal -30%")
- Categorie esplorabili (Farmaci 💊, Materiale 🩹, Diagnostica 🔬)
- Offerte flash con badge "Flash" e timer
- Prezzi scontati vs originali con evidenziazione

**Dati visualizzati:**
- Stock Vaccini Core Annuale: -30%
- Antiparassitari Spot-On: €145 (era €210)
- Kit Bende Coesive: €89 (era €120)

#### 🔔 Alert
**Funzionalità attuali:**
- Notifiche offerte esclusive con immagini
- Alert stock (riordino disponibile)
- Trend prezzi (flessioni rilevate, es. "-4% Ketamina")
- Badge e azioni rapide ("Approfitta", "Monitora")

### 1.3 Schema Database (Convex)

| Tabella | Campi Principali | Relazioni |
|---------|-----------------|-----------|
| `clinics` | name, address, city, province, isActive | → veterinarians, purchases, rebates |
| `veterinarians` | clinicId, firstName, lastName, role | → clinics |
| `medicines` | name, category, eanCode, unitPrice | → purchaseItems, purchaseGroups |
| `purchases` | clinicId, purchaseDate, supplier, totalAmount, status | → clinics, purchaseItems |
| `purchaseItems` | purchaseId, medicineId, quantity, unitPrice, totalPrice | → purchases, medicines |
| `rebates` | clinicId, supplier, rebateType, value | → clinics |
| `purchaseGroups` | name, organizerId, medicineId, targetQuantity, status | → clinics, medicines |
| `purchaseGroupParticipants` | groupId, clinicId, quantity, status | → purchaseGroups, clinics |

### 1.4 Sistema di Autenticazione

| Account | Email | Password | Ruolo | Clinica |
|---------|-------|----------|-------|---------|
| Owner | demo@vetunita.it | demo123 | owner | Clinica Veterinaria Milano |
| Veterinario | vet@vetunita.it | vet123 | veterinarian | Ambulatorio Veterinario Roma |

---

## 🎯 2. PIVOT STRATEGICO - BENCHMARKING & CLUSTERING

### 2.1 Visione

**Trasformare VetUnitaApp da semplice catalogo/offerte a piattaforma di intelligence competitiva per cliniche veterinarie.**

L'obiettivo è dare in mano al proprietario della clinica strumenti concreti per:
- Confrontare i propri prezzi con quelli del network
- Capire se sta pagando troppo rispetto ad altre cliniche simili
- Scoprire opportunità di risparmio basate su dati reali
- Partecipare a gruppi d'acquisto intelligenti

### 2.2 Funzionalità Principali da Aggiungere

#### 📊 A. Benchmarking Prezzi Farmaci

**Cosa vede l'utente nel catalogo:**

```
┌─────────────────────────────────────────┐
│  AmoxiClav Premium                      │
│  Antibiotico Ad Ampio Spettro           │
│                                         │
│  Il tuo prezzo:     $99.20              │
│  Media Network:     $87.50              │
│  Min Network:       $72.00              │
│  Max Network:       $124.00             │
│                                         │
│  ⚠️  Paghi il 13% in più della media   │
│  💡 Risparmio potenziale: $11.70        │
│                                         │
│  [Partecipa al Gruppo d'Acquisto]      │
└─────────────────────────────────────────┘
```

**Dati da mostrare per ogni farmaco:**
- Prezzo pagato dalla propria clinica
- Prezzo medio pagato dal network
- Prezzo minimo e massimo nel network
- Indicatore visivo (🟢 sotto media, 🟡 nella media, 🔴 sopra media)
- Calcolo risparmio potenziale

#### 🏷️ B. Clustering Cliniche

**Algoritmo di clustering dal backend CRM:**

Criteri di segmentazione:
1. **Volume acquisti annuo**
   - Small: < €50K/anno
   - Medium: €50K - €200K/anno
   - Large: €200K - €500K/anno
   - Enterprise: > €500K/anno

2. **Categorie di farmaci più acquistate**
   - Generalista (distribuzione uniforme)
   - Dermatologica (focus antiparassitari)
   - Chirurgica (focus antibiotici, anestetici)
   - Specializzata (focus su nicchie)

3. **Dimensione clinica**
   - 1-2 veterinari
   - 3-5 veterinari
   - 6+ veterinari

4. **Zona geografica**
   - Nord, Centro, Sud, Isole

**Cluster di esempio:**
```
Cluster: "Small Generalist North"
- Cliniche simili: 47
- Volume medio: €35K/anno
- Farmaci top: Antibiotici, Vaccini, FANS
- Prezzo medio AmoxiClav: €82.50
```

#### 📈 C. Dashboard Confronti Network

**Nuova sezione nella Dashboard:**

```
┌─────────────────────────────────────────┐
│  📊 Confronto Network                   │
│                                         │
│  Il tuo cluster: Small Generalist North │
│  Cliniche simili: 47                    │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │  AmoxiClav Premium              │   │
│  │  ▓▓▓▓▓▓▓▓░░  $99.20 (Tu)      │   │
│  │  ▓▓▓▓▓▓░░░░  $87.50 (Media)    │   │
│  │  ▓▓▓▓░░░░░░  $72.00 (Min)      │   │
│  └─────────────────────────────────┘   │
│                                         │
│  🏆 Sei nel top 30% per efficienza      │
│  💰 Risparmio potenziale: €2,340/anno   │
└─────────────────────────────────────────┘
```

**Elementi:**
- Grafico a barre comparativo (tu vs media vs min)
- Posizionamento nel cluster
- Classifica efficienza acquisti (anonimizzata)
- Alert opportunità di risparmio

#### 🔔 D. Alert Prezzi Personalizzati

**Tipologie di alert intelligenti:**

1. **Alert "Stai pagando troppo"**
   ```
   ⚠️ Il farmaco AmoxiClav Premium lo paghi $99.20
   La media del network è $87.50
   Risparmio potenziale: $11.70 per scatola
   ```

2. **Alert "Opportunità"**
   ```
   💡 Il farmaco Bravecto è sceso sotto la media del network!
   Prezzo attuale: $32.50 (media: $38.00)
   [Approfitta ora]
   ```

3. **Alert "Cluster"**
   ```
   📊 12 cliniche del tuo cluster hanno appena formato
   un gruppo d'acquisto per Zoetis Vaccini.
   [Partecipa]
   ```

#### 🤝 E. Gruppi d'Acquisto Intelligenti

**Funzionalità:**
- Suggerimenti automatici basati sul clustering
- "Cliniche simili alla tua hanno formato un gruppo per questo farmaco"
- Partecipazione one-tap
- Tracking progresso gruppo (quantità raccolta vs target)
- Notifiche quando il gruppo raggiunge il target

### 2.3 User Journey

```
[Login] → [Dashboard]
              │
              ├─→ "Vedi i tuoi risparmi" → [Savings Card]
              │
              ├─→ "Confronta con il network" → [Benchmarking Section]
              │        │
              │        ├─→ Prezzo tuo vs media vs min/max
              │        ├─→ Grafico comparativo
              │        └─→ Alert opportunità
              │
              ├─→ "Catalogo" → [Farmaci con badge network]
              │        │
              │        ├─→ Ogni farmaco mostra:
              │        │   - Prezzo tuo
              │        │   - Media network
              │        │   - Min/Max
              │        │   - Indicatore verde/giallo/rosso
              │        │
              │        └─→ [Partecipa al gruppo d'acquisto]
              │
              └─→ "Alert" → [Notifiche intelligenti]
                         │
                         ├─→ "Stai pagando troppo per X"
                         ├─→ "Opportunità per Y"
                         └─→ "Nuovo gruppo d'acquisto disponibile"
```

---

## 🔧 3. MODIFICHE TECNICHE RICHIESTE

### 3.1 Backend (Convex)

#### Nuove Tabelle

```typescript
// Benchmarking prezzi per farmaco
priceBenchmarks: defineTable({
  medicineId: v.id("medicines"),
  networkAvgPrice: v.number(),      // Media network
  networkMinPrice: v.number(),      // Minimo network
  networkMaxPrice: v.number(),      // Massimo network
  clinicPrice: v.number(),          // Prezzo della clinica
  percentile: v.number(),           // Percentile (0-100)
  lastUpdated: v.number(),
})
  .index("by_medicine", ["medicineId"])
  .index("by_clinic", ["clinicId"]),

// Assegnazione cluster per clinica
clinicClusters: defineTable({
  clinicId: v.id("clinics"),
  clusterId: v.string(),            // es. "small_generalist_north"
  clusterName: v.string(),          // es. "Small Generalist North"
  clusterSize: v.number(),          // Numero cliniche nel cluster
  annualVolume: v.number(),         // Volume acquisti annuo
  topCategories: v.array(v.string()), // Categorie top
  avgPriceIndex: v.number(),        // Indice prezzo medio (100 = media)
  efficiencyScore: v.number(),      // Punteggio efficienza (0-100)
  assignedAt: v.number(),
})
  .index("by_clinic", ["clinicId"])
  .index("by_cluster", ["clusterId"]),

// Opportunità di risparmio
savingsOpportunities: defineTable({
  clinicId: v.id("clinics"),
  medicineId: v.id("medicines"),
  currentPrice: v.number(),
  networkAvgPrice: v.number(),
  potentialSavings: v.number(),
  savingsPercentage: v.number(),
  status: v.string(),               // "new", "viewed", "acted"
  createdAt: v.number(),
})
  .index("by_clinic", ["clinicId"])
  .index("by_medicine", ["medicineId"])
  .index("by_status", ["status"]),
```

#### Nuove Query/Mutation

```typescript
// Query benchmarking per farmaco
export const getMedicineBenchmark = query({
  args: { medicineId: v.id("medicines"), clinicId: v.id("clinics") },
  handler: async (ctx, args) => {
    // Calcola min/med/max dal network
    // Confronta con prezzo della clinica
    // Restituisci benchmark completo
  },
});

// Query cluster della clinica
export const getClinicCluster = query({
  args: { clinicId: v.id("clinics") },
  handler: async (ctx, args) => {
    // Restituisci cluster di appartenenza
    // Con statistiche del cluster
  },
});

// Query opportunità di risparmio
export const getSavingsOpportunities = query({
  args: { clinicId: v.id("clinics"), limit: v.optional(v.number()) },
  handler: async (ctx, args) => {
    // Restituisci lista opportunità
    // Ordinate per risparmio potenziale
  },
});

// Mutation per unirsi a gruppo d'acquisto
export const joinPurchaseGroup = mutation({
  args: { groupId: v.id("purchaseGroups"), quantity: v.number() },
  handler: async (ctx, args) => {
    // Aggiungi partecipazione
    // Aggiorna quantità corrente del gruppo
  },
});
```

### 3.2 Frontend (App)

#### Nuovi Componenti UI

```
src/components/
├── benchmarking/
│   ├── PriceComparisonCard.tsx      // Card confronto prezzi
│   ├── ClusterBadge.tsx             // Badge cluster
│   ├── SavingsOpportunity.tsx       // Card opportunità
│   └── NetworkPriceIndicator.tsx    // Indicatore min/med/max
├── charts/
│   ├── BarComparisonChart.tsx       // Grafico a barre comparativo
│   └── PriceDistributionChart.tsx   // Distribuzione prezzi
└── groups/
    ├── PurchaseGroupCard.tsx        // Card gruppo d'acquisto
    └── GroupProgress.tsx            // Barra progresso gruppo
```

#### Nuove Screen

```
src/app/(tabs)/
├── dashboard.tsx          (modificato - aggiunta sezione confronti)
├── catalogo.tsx           (modificato - aggiunto benchmarking per farmaco)
├── offerte.tsx            (modificato - aggiunto alert cluster)
├── alert.tsx              (modificato - aggiunto alert prezzi)
└── confronti.tsx          (NUOVO - dashboard completa confronti)
```

#### Dipendenze da Aggiungere

```json
{
  "dependencies": {
    "react-native-chart-kit": "^6.12.0",
    "react-native-svg": "^15.0.0"
  }
}
```

### 3.3 Backend CRM (Algoritmo di Clustering)

**Stack consigliato:**
- Python con scikit-learn per clustering K-Means
- Oppure Node.js con ml-kmeans

**Feature per clustering:**
```python
features = [
    'annual_volume',          # Volume acquisti annuo
    'num_veterinarians',      # Numero veterinari
    'antibiotics_percentage', # % acquisti antibiotici
    'vaccines_percentage',    # % acquisti vaccini
    'fns_percentage',         # % acquisti FANS
    'geographic_zone',        # Zona geografica (codificata)
]

# K-Means con 4-6 cluster
from sklearn.cluster import KMeans
kmeans = KMeans(n_clusters=5)
clusters = kmeans.fit_predict(features)
```

---

## 📅 4. ROADMAP DI IMPLEMENTAZIONE

### Fase 1: Foundation (2-3 settimane)
- [ ] Estendere schema Convex con tabelle benchmarking
- [ ] Creare query per calcolo prezzi network
- [ ] Implementare algoritmo di clustering nel CRM
- [ ] Popolare dati di benchmarking da acquisti storici

### Fase 2: UI Components (2 settimane)
- [ ] Creare componenti PriceComparisonCard
- [ ] Creare ClusterBadge e NetworkPriceIndicator
- [ ] Integrare grafici a barre nella dashboard
- [ ] Aggiungere badge network alle card del catalogo

### Fase 3: Alert & Opportunities (1-2 settimane)
- [ ] Implementare sistema alert prezzi
- [ ] Creare sezione opportunità di risparmio
- [ ] Aggiungere alert "stai pagando troppo"
- [ ] Notifiche push per opportunità

### Fase 4: Smart Groups (2 settimane)
- [ ] Migliorare sistema gruppi d'acquisto
- [ ] Aggiungere suggerimenti basati su clustering
- [ ] Implementare tracking progresso gruppo
- [ ] UI per partecipazione one-tap

### Fase 5: Polish & Analytics (1-2 settimane)
- [ ] Dashboard completa confronti
- [ ] Classifica efficienza (anonimizzata)
- [ ] Trend storici dei prezzi
- [ ] Report esportabile per clinica

---

## 📊 5. METRICHE DI SUCCESSO

| Metrica | Target |
|---------|--------|
| Engagement benchmarking | 60% utenti attivi lo usano settimanalmente |
| Partecipazione gruppi | 30% degli utenti si unisce a ≥1 gruppo/mese |
| Risparmio medio | 15% riduzione costi farmaci entro 6 mesi |
| Retention | 80% retention dopo 3 mesi (vs 50% attuale) |
| NPS | 50+ (da misurare) |

---

## 📝 6. NOTE TECNICHE

### Considerazioni Privacy
- Tutti i dati di benchmarking sono **anonimizzati**
- Nessun utente può vedere i prezzi specifici di altre cliniche
- Solo aggregate: media, min, max, percentile
- Cluster identificati da nome, non da cliniche specifiche

### Performance
- Benchmarking calcolato in background (cron job giornaliero)
- Cache dei risultati per 24 ore
- Aggiornamento real-time solo per dati della propria clinica

### Scalabilità
- Schema progettato per supportare 1000+ cliniche
- Indici ottimizzati per query frequenti
- Paginazione per liste opportunità

---

## 🚀 Conclusione

Il pivot verso il **benchmarking e clustering** trasforma VetUnitaApp da catalogo passivo a **piattaforma di intelligence attiva**, dando alle cliniche veterinarie il potere di:

1. **Conoscere** il vero valore di mercato dei farmaci
2. **Confrontarsi** con cliniche simili in modo anonimo
3. **Risparmiare** grazie a dati concreti e opportunità mirate
4. **Collaborare** attraverso gruppi d'acquisto intelligenti

Questo posizionamento unico nel mercato veterinario italiano crea un **moat competitivo** basato sui dati, difficile da replicare per concorrenti che non hanno una rete di cliniche connesse.

---

*Documento creato il 23/04/2026*
*Versione 1.0*
```

### [TEXT] example.txt
```

```

---

## 2. Inventario UI (Estratto da HTML)

*Nessun file HTML trovato.*

---

## 3. Screenshots UI (Analizzati con Vision)

*Nessuno screenshot trovato.*

---

## 4. Modello Dati (Inferito)

Basato sull'analisi dei form e degli input HTML:

*Nessun campo dati inferito dai form HTML.*

---

## 5. Endpoint API (Inferiti)

Basato sull'analisi delle action dei form:

*Nessun endpoint API inferito.*

---

## 6. Note per l'Agente Analista

Questo contesto è stato generato automaticamente. Utilizzalo come base per:

1. **Generare i flussi utente** (User Journey)
2. **Definire gli stati dell'applicazione** (State Machine)
3. **Identificare gli edge case** (gestione errori, stati limite)
4. **Creare diagrammi Mermaid** (Flowchart, Sequence Diagram)
5. **Generare configurazione XState** eseguibile

### Checklist per l'analisi:
- [ ] Ogni form ha uno stato di caricamento definito?
- [ ] Ogni chiamata API ha gestione errori 4xx e 5xx?
- [ ] C'è un modo per annullare ogni operazione intermedia?
- [ ] Cosa succede se l'utente perde la connessione?
- [ ] Cosa succede se l'utente preme "indietro" nel browser?
- [ ] Gli stati di errore mostrano messaggi chiari all'utente?
- [ ] C'è un modo per recuperare da uno stato di errore?

