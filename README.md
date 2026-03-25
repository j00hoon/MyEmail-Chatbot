# myEmail-chatbot

## Backend Run Guide

This project uses:

- A Python virtual environment in `backend/venv`
- Redis running in Docker
- A Flask backend on port `5000`

## Start Everything At Once

From the project root, run:

```powershell
.\start-all.ps1
```

What this script does:

- Checks whether the `redis` Docker container already exists
- Creates it if needed, or starts it if it is stopped
- Starts the Flask backend with the Python executable inside `backend/venv`
- Starts the React frontend dev server on port `5173`
- Opens the frontend URL in your default browser automatically

## Manual Run

If you want to start each step manually:

```powershell
docker start redis
cd backend
.\venv\Scripts\activate
python app.py
```

Or without activating the virtual environment:

```powershell
docker start redis
.\backend\venv\Scripts\python.exe .\backend\app.py
```

## Backend URL

When the server starts successfully, it runs at:

```text
http://127.0.0.1:5000
```

Email data API:

```text
http://127.0.0.1:5000/api/emails
```

You can also request a specific number of emails:

```text
http://127.0.0.1:5000/api/emails?count=10
```

## Frontend Run Guide

The frontend was created with Vite + React and uses `axios` for API calls.

From the project root:

```powershell
cd frontend
npm run dev
```

Vite will print a local development URL in the terminal, usually:

```text
http://127.0.0.1:5173
```

If you use `.\start-all.ps1`, you do not need to type the frontend URL manually in most cases because the script opens the browser for you. If the browser does not open, enter this URL manually:

```text
http://127.0.0.1:5173
```

## Stop Everything

To stop the frontend, backend, and Redis container:

```powershell
.\stop-all.ps1
```
