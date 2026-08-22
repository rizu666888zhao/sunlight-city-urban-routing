# Sunlight City - Urban Comfort Analysis Platform

Sunlight City is a front-end demo platform for evaluating urban walking and cycling comfort. It is well suited for demonstrating data visualization, interactive maps, and real-time metrics.

## 🌟 Features

### Core features
- **Interactive map** — Visualize key city locations and comfort data
- **City selection / account menu** — Top bar supports city switching (Manhattan by default) and an account menu
- **Real-time data panel (environmental factors)** — Dynamically shows temperature, humidity, wind speed, UV index, and other environmental factors (segment-level shade coverage not included)
- **Comfort analysis** — Analyze comfort trends for pedestrian and cycling routes by time of day and month
- **3D city model** — Supports 3D model display (extensible)
- **Data visualization** — Advanced charts and trend analysis with Recharts

### Research focus
- **Shade coverage analysis** — Dynamic shade calculation based on solar trajectory
- **Temperature and humidity** — Real-time environmental monitoring
- **Pedestrian comfort** — Composite comfort score from multiple factors
- **Cycling routes** — Targeted evaluation for bicycle users

## 🛠 Tech stack

- **Front end**: Next.js 14 + React 18 (TypeScript)
- **Styling**: Tailwind CSS
- **Charts**: Recharts
- **Icons**: Lucide React
- **Visualization**: Three.js (supported)
- **Maps**: Mapbox GL (integration-ready)

**Back end (demo)**:
- **API framework**: FastAPI (Python)
- **Database**: PostgreSQL (asyncpg)
- **Auth**: JWT (python-jose) + pbkdf2_sha256 (passlib)
- **Async ORM**: SQLAlchemy 2.0+ (async)

> This repo includes a lightweight back end under `/server` for local demos of user registration, login, and sessions (FastAPI + PostgreSQL). See `server/README.md` for setup details and API documentation.

## 📦 Install and run

### Prerequisites
- Node.js 18+
- npm or yarn

### Install dependencies
```bash
npm install
```

### Full local test (front end + back end)
Run both the API and the front end so login/registration, trips, and related features work.

1. **Back end** (one terminal at the project root):
   ```bash
   server/.venv/bin/python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
   ```
   On first run, configure `server/.env` (see `server/README.md`) and create a virtual environment:  
   `python3 -m venv server/.venv` and `server/.venv/bin/pip install -r server/requirements.txt`.

2. **Front end** (another terminal):
   ```bash
   npm run dev
   ```

3. Open http://localhost:3000 in the browser; the API is at http://localhost:8000 (docs: http://localhost:8000/docs).

### Production build
```bash
npm run build
npm start
```

### Deploy to Vercel (front end + back end together)
The project is set up to run Next.js and FastAPI (Python functions under `/api`) on Vercel. After deployment, set these environment variables in the Vercel project settings:

**Required:**
- `DATABASE_URL` — Supabase connection string, format: `postgresql+asyncpg://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres?ssl=require`
- `SECRET_KEY` — Secret for JWT signing (use a strong random string in production)
- `ALLOWED_ORIGINS` — Allowed CORS origins, comma-separated, e.g.: `https://your-project.vercel.app,https://sunlight-city-blush.vercel.app`
- `NEXT_PUBLIC_API_BASE` — Base URL the front end uses for the API; after deployment use `https://your-project.vercel.app/api` (same origin as the site is fine)

Redeploy after configuration; login/registration will use FastAPI on Vercel and connect to Supabase.

## 📁 Project structure

```
src/
├── app/
│   ├── layout.tsx          # Root layout
│   ├── page.tsx            # Main page
│   └── globals.css         # Global styles
├── components/
│   ├── Dashboard.tsx       # Main dashboard
│   ├── Header.tsx          # Page header
│   ├── Sidebar.tsx         # Left navigation
│   ├── MapView.tsx         # Interactive map
│   ├── DataPanel.tsx       # Data analysis panel
│   └── RealTimeData.tsx    # Real-time data display
└── lib/                    # Utilities
```

## 🎨 UI characteristics

- **Modern dark theme** — Dark UI tuned for long sessions
- **Responsive layout** — Works across screen sizes
- **Gradient accents** — Clear visual hierarchy
- **Real-time motion** — Smooth interactions and transitions
- **Information density** — Complex data shown efficiently

## 🗺 Main views

### Map view
- Interactive city map
- Location markers and comfort indicators
- Quick access to key places

### Analysis view
- Daily comfort curves
- Year-round trend analysis
- Key metric cards
- Location details

### 3D model view
- 3D building models
- Shadow projection visualization
- Compare multiple time windows

## 📊 Data metrics

- **Temperature** — Real-time temperature (°C)
- **Humidity** — Relative humidity (%)
- **Wind speed** — Wind speed (m/s)
- **UV index** — UV Index (0–11)
- **Comfort index** — Composite score (0–100%)
- **Shade coverage** — Sun/shade coverage (%)

## 🚀 Roadmap

- [ ] Real-time weather API integration
- [ ] Mapbox map integration
- [ ] Three.js 3D model implementation
- [ ] Database and back-end API
- [ ] User authentication system
- [ ] Data export
- [ ] Mobile app support

## 📝 Development notes

### Adding components
1. Add a new `.tsx` file under `src/components/`
2. Use the `'use client'` directive for client components
3. Import and use it from the Dashboard

### Styling
- Edit `tailwind.config.ts` to customize theme colors
- Use Tailwind CSS utility classes
- Global styles live in `src/app/globals.css`

### Wiring real data
1. Add `src/lib/api.ts` for API calls
2. Fetch data in components with `useEffect`
3. Update state management as needed
