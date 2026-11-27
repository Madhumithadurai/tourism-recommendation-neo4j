# TripGraph Live: Interactive Tourism Recommendation System using Neo4j

Micro Project 12 · Research focus: tourism, travel and recommendation services.

An interactive 3D simulator in the browser. South India's destinations stand as towers on a map
and routes run between them as tubes. You click, drag sliders and change the environment, and the
graph answers live from Neo4j.

| Layer    | Technology |
|----------|------------|
| Frontend | HTML, CSS, JavaScript (ES modules) + **Three.js 0.160** for the 3D map (bundled in `frontend/vendor`, works offline) |
| Backend  | Python 3 + Flask, official Neo4j Python driver |
| Database | Neo4j 5.x, plain Cypher (no plugins) |

---

## 1. What you can do (practicals)

### 🧭 Route Lab: route discovery, connected destinations, alternative paths
* **Click two towns** on the 3D map. The search runs **step by step**: frontier towns pulse,
  expanded towns turn teal, relaxed roads flash yellow, and the **live priority queue** shows what is
  expanded next. Speed slider, **Step** and **Instant** buttons.
* Choose **Dijkstra, A\*, BFS or Greedy**. Optimise **time, distance or cost**. Toggle
  **road / rail / flight**.
* When the route is found, a **traveller drives it** with live hours, km, cost and progress.
* **Change the world while it drives.**
  * Tools: ⛔ close a road, 🚦 add traffic (×2, ×3), ➕ build a new route, 🧽 clear.
  * Environments: *Monsoon* (ghat roads closed), *Rail strike*, *Flights grounded*,
    *Festival rush*, *Coastal cyclone*.
  * The traveller **re-routes** from the next town (or turns back if its own road closes) and
    counts re-routes. If the goal is cut off, it stops and says so.
* **Race all algorithms**: towns expanded, edges relaxed, cost and which ones are optimal.
* **Show 3 alternatives** (Yen's algorithm) and drive any of them.
* **✔ Verify in Neo4j** runs the same question as Cypher, with your closures and traffic as
  parameters. It shows whether Neo4j and the browser agree.
* **💾 Save scenario** writes closures, traffic and new routes into Neo4j (`r.closed`,
  `r.trafficFactor`, new `ROUTE`s). **↺ Restore** removes them.

### 🗺️ Explore: destination discovery
* **Interest match:** toggle interest chips (🏖️ Beach, 🐘 Wildlife…), slide the month and pick a
  budget. Towers grow and glow by match score from a live Cypher query, the top 3 get light beams,
  and the ranking list re-orders with animation.
* **Reachable area:** pick a town and slide *within N hours*. The reachable area lights up and
  spreads as you slide; toggle travel modes.
* Click any tower for its attractions, ratings, entry fees, visits, hotels and best months.

### ✨ Recommend: personalised recommendations
* Pick one of 20 tourists. Their **interest sliders** load from Neo4j. Drag a slider or change the
  month and everything **re-ranks live**:
  * top destinations, with reasons: interests, season, hours from home;
  * a hybrid attraction list that marks where each item came from (C = content-based, F = similar
    tourists).
  * On the map, beams rise on the recommended destinations and a green route runs from home to the
    top pick.
* Click an attraction to see **why** (a graph of the connecting paths). Press **I visited it ★…★**
  to write a real `VISITED` relationship and watch the recommendations change. **Undo demo visits**
  removes them.

### 🧱 Build graph: data population
* **Build everything** runs the constraint and data steps one by one. The 3D graph **grows** as you
  watch: destinations, then routes, then attractions (towers get taller).
* A clickable graph model, live node and relationship counters, and the **🩺 Pre-demo check**.

### 📊 Evaluate
* Live leave-one-out evaluation. Tourist by tourist, the scoreboard fills in (green = in top 5,
  amber = in top 10) and the Hit@5, Hit@10, MRR and coverage bars animate for popularity,
  content-based, collaborative and hybrid.

### ⌨️ Cypher
* A library of all 26 project queries: one click loads the query with sample parameters and runs
  it, showing a table and a draggable graph.

---

## 2. Install the prerequisites
1. **Python 3.10–3.12**: https://www.python.org/downloads/ (Windows: tick *Add python.exe to PATH*).
2. **Neo4j 5.x**: **Neo4j Desktop** is easiest (https://neo4j.com/download/). Community Server or
   Docker also work:
   `docker run -d -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/tripgraph123 neo4j:5`
3. **Browser:** Chrome or Edge (any browser with WebGL; laptops with integrated graphics are fine).

## 3. Configure and run
1. **Create the database.** In Neo4j Desktop: *New* → local instance, password for example
   `tripgraph123` → **Start**.
2. **Install the backend.**
   ```
   cd tripgraph-live\backend
   python -m venv .venv
   .venv\Scripts\activate             (Linux/macOS: source .venv/bin/activate)
   pip install -r requirements.txt
   copy .env.example .env              (Linux/macOS: cp .env.example .env)
   ```
   Open `.env` and set `NEO4J_PASSWORD=tripgraph123`.
3. **Start the app.** Run `python app.py` (or `start_windows.bat` / `./start_linux_mac.sh`), then
   open **http://127.0.0.1:5000**.
4. **Load the data.** The app opens on **🧱 Build graph** while the database is empty. Press
   **▶ Build everything**.

   Alternatively, in Neo4j Browser run `neo4j/01_constraints.cypher` and then
   `neo4j/02_sample_data.cypher`. `neo4j/03_queries.cypher` holds every query with sample values,
   ready to run without parameters.
5. **Check.** Press **🩺 Pre-demo check**. Every line should be green. It runs every query and
   feature against your database.

---

## 4. Suggested 10-minute demonstration
1. **Build graph:** press *Build everything* and let the graph grow (1 min).
2. **Route Lab:**
   1. Click **Chennai**, then **Munnar**, and watch Dijkstra search. It drives Chennai → Kochi → Munnar.
   2. While it drives, pick ⛔ and close **Kochi–Munnar**. It re-routes via Alappuzha and Thekkady.
   3. Switch to **A\*** and press *Race all algorithms*: A\* expands fewer towns and is still optimal.
   4. Choose the **Monsoon** environment and try again. Munnar is cut off by road.
   5. Press **Verify in Neo4j**, then **Save scenario**.
3. **Explore:** toggle *Wildlife* and *Hill Station* and slide the month. Then switch to *Reachable
   area* from Chennai and slide from 3 h to 10 h.
4. **Recommend:** pick a tourist, drag *Wildlife* to 3 and watch the list re-rank. Open *why* on an
   attraction and mark it visited.
5. **Evaluate:** press *Run evaluation* and discuss why content-based and hybrid beat the popularity
   baseline, while collaborative filtering suffers from sparsity with only 20 tourists.

---

## 5. How it works

```
Browser (Three.js scene, algorithms.js)  ──HTTP/JSON──>  Flask (app.py, core/live.py)  ──Bolt──>  Neo4j
  · animates searches step by step                         · runs Cypher, returns rows + Cypher text
  · Dijkstra / A* / BFS / Greedy / Yen in JS               · recommendations, scenarios, verification
```
* **Graph model:** `(:Tourist)`, `(:Destination)`, `(:Attraction)`, `(:Category)`, `(:Hotel)`.
  Relationships: `ROUTE {mode, distanceKm, hours, costInr, closed?, trafficFactor?, added?}`,
  `LOCATED_IN`, `HAS_CATEGORY`, `INTERESTED_IN {weight}`, `VISITED {date, rating, demo?}`,
  `STAYED_AT`, `LIVES_IN` and `WISHLISTED`.
* **Sample data:** 25 real destinations, 53 routes (road, rail, flight), 58 real attractions,
  63 fictional hotels and 20 fictional tourists: 178 nodes and 609 relationships. Distances, hours
  and costs are rounded estimates.
* **Algorithms in the browser** are written as generators, so each step can be drawn.
  * The A\* heuristic is the straight-line distance divided by the fastest straight-line speed in
    the data, so it never over-estimates and stays optimal.
  * The same results are checked against Python (tests) and against Cypher ("Verify in Neo4j").
* **Live recommendations:**
  * Content-based scoring uses Cypher with your slider weights as a parameter (`UNWIND $weights`).
  * Collaborative filtering uses Jaccard similarity of visits with the 5 nearest tourists.
  * The hybrid combines them with reciprocal rank fusion.
  * Destinations are scored on interest, season and travel time from home.
* Every live panel has a **Cypher** drawer showing the exact query that produced it.

## 6. Folder structure
```
tripgraph-live/
├── backend/
│   ├── app.py              Flask API + serves the frontend
│   ├── core/live.py        network, explore, details, live recommendations, visits, scenarios, verify
│   ├── core/catalog.py     the 26 Cypher queries (route queries honour closures and traffic)
│   ├── core/recommend.py   rank fusion + evaluation      core/routing.py  Python planner
│   ├── data/tourism.py     sample data                    tools/generate_cypher.py
│   └── tests/              26 tests (no database needed)
├── frontend/
│   ├── index.html, css/style.css
│   ├── js/  app, scene (3D), algorithms, routelab, explore, recommend, build, evaluate, console, graph2d, util
│   └── vendor/  three.module.min.js, OrbitControls.js, CSS2DRenderer.js (MIT licence)
└── neo4j/  01_constraints, 02_sample_data, 03_queries, 99_reset (.cypher)
```

## 7. Troubleshooting
| Problem | Fix |
|---|---|
| Badge says *Neo4j offline* | Start the database; check `NEO4J_PASSWORD` in `backend/.env`; restart `python app.py`. |
| The map is empty | Build the graph (🧱 page) or run scripts 01 and 02. |
| Black map area | The browser has WebGL turned off: use Chrome or Edge and enable hardware acceleration. |
| Page opened as a file shows nothing | Always open http://127.0.0.1:5000 (ES modules need the server). |
| A red line in the Pre-demo check | Send the message shown. It is the exact Neo4j error. |
| Recommendations look odd after demos | Press *Undo demo visits*. On Route Lab press *Restore network*. |

## 8. Tests
`python -m unittest discover -s tests -v` (from `backend`) checks the data, scripts, query
catalogue, routing (against brute force), live-page logic, scenario validation and the bundled
frontend files.
