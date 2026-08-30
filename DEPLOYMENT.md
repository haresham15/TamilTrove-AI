# TamilTrove Deployment Guide

This guide will walk you through deploying your full-stack AI application completely for free. 
We will host the **Python FastAPI Backend on Render** and the **Next.js Frontend on Vercel**.

---

## 🛠 Step 1: Prepare Your GitHub Repository

Both Render and Vercel will pull your code directly from GitHub.

1. **Initialize Git (if you haven't already):**
   Open a terminal in the root of your project (`TamilMoviesSort`) and run:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for deployment"
   ```

2. **CRITICAL: Ensure Data Files are Committed!**
   Your backend relies on the precomputed data to boot up instantly. Make sure `backend/data/movies_processed.json` and `backend/data/embeddings.npy` are NOT in your `.gitignore` file. They must be pushed to GitHub for the backend to work.

3. **Push to GitHub:**
   Create a new repository on [GitHub](https://github.com/), and push your code:
   ```bash
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
   git push -u origin main
   ```

---

## 🚀 Step 2: Deploy the Backend on Render (Free Tier)

Render provides a fantastic free tier for Python web services.

1. Go to [Render.com](https://render.com/) and sign up using your GitHub account.
2. Click **New +** and select **Web Service**.
3. Connect your GitHub account and select your `TamilMoviesSort` repository.
4. **Configure the Service:**
   - **Name:** `tamiltrove-backend` (or whatever you prefer)
   - **Root Directory:** `backend` (This is crucial!)
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`
   - **Environment Variable:** Set `ALLOWED_ORIGINS` to your frontend URL. Multiple origins can be supplied as a comma-separated list.
5. Click **Create Web Service**. 
6. Render will now download your requirements (including SentenceTransformers and Scikit-learn). *Note: The first build might take 3-5 minutes.*
7. Once deployed, you will get a URL like `https://tamiltrove-backend.onrender.com`. Copy this URL!

> **Warning for Free Tier**
> Render's free tier "spins down" your backend after 15 minutes of inactivity. When a user visits your app after a period of inactivity, the very first search might take ~30-50 seconds as the server wakes up and loads the AI models. 

---

## ⚡ Step 3: Deploy the Frontend on Vercel (Free Tier)

Vercel is the creator of Next.js and provides the absolute best hosting for it.

1. Go to [Vercel.com](https://vercel.com/) and sign up with your GitHub account.
2. Click **Add New...** and select **Project**.
3. Import your `TamilMoviesSort` repository from GitHub.
4. **Configure the Project:**
   - **Project Name:** `tamiltrove`
   - **Root Directory:** Click "Edit" and select `frontend`. (This tells Vercel to look in the frontend folder for Next.js).
5. **Set Environment Variables:**
   - Expand the **Environment Variables** section.
   - **Name:** `NEXT_PUBLIC_API_URL`
   - **Value:** Paste the URL you got from Render in Step 2 (e.g., `https://tamiltrove-backend.onrender.com`).
   - Click **Add**.
6. Click **Deploy**.

Vercel will build your Next.js application. Once it finishes (usually < 2 minutes), you'll get a production URL where your fully functional AI app is live!

---

## 🎉 Step 4: Add to your Resume / Portfolio!

You now have a production-ready URL! 

When talking to AI/ML recruiters, be sure to highlight this specific architecture:
- **Frontend:** React / Next.js (Hosted on Vercel)
- **Backend:** Python / FastAPI (Hosted on Render)
- **AI Core:** SentenceTransformers (`all-MiniLM-L6-v2`) for semantic embeddings.
- **Data Engineering:** Automated web-scraping and cross-referencing Wikipedia APIs for data augmentation.
- **Mathematical Modeling:** Real-time Principal Component Analysis (PCA) via Scikit-learn for dimensionality reduction and visualization of semantic clustering.
- **Algorithm:** Custom Maximal Marginal Relevance (MMR) scoring logic for result diversity with dynamic, similarity-gated "Hidden Gem" boosting.
