import psycopg2
import googlemaps
from os import getenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = getenv("DATABASE_URL")
GOOGLE_PLACES_KEY = getenv("GOOGLE_PLACES_KEY")

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

def calculate_score(place_data):
    """Calcula score 0-100 baseado em Google Places data"""
    score = 50  # Base score

    # +10 se tem foto
    if place_data.get('photos'):
        score += 10

    # +15 se tem rating
    if place_data.get('rating'):
        score += 15

    # +10 se tem reviews
    if place_data.get('user_ratings_total', 0) > 0:
        score += 10

    # +15 se perfil completo (website, phone, etc)
    if place_data.get('website') or place_data.get('formatted_phone_number'):
        score += 15

    return min(100, score)  # Cap at 100

app = FastAPI(title="SEO Local API")

# CORS - Restrict to frontend origin
ALLOWED_ORIGINS = getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

gmaps = googlemaps.Client(key=GOOGLE_PLACES_KEY) if GOOGLE_PLACES_KEY else None

@app.get("/")
def read_root():
    return {"message": "SEO Local API - Running"}

@app.post("/audit")
def audit_gbp(url: str):
    try:
        if not gmaps:
            raise HTTPException(status_code=500, detail="Google Places API not configured")

        # Extract domain from URL
        domain = url.replace("https://", "").replace("http://", "").split("/")[0]

        # Search for business in Google Places
        result = gmaps.places(query=domain)

        if not result.get('results'):
            return {"error": "Business not found on Google Places", "score": 0}

        place = result['results'][0]
        score = calculate_score(place)

        # Save to database - make failure explicit
        audit_id = None
        audit_saved = False
        try:
            conn = get_db_connection()
            cur = conn.cursor()

            cur.execute(
                "INSERT INTO audits (url, score) VALUES (%s, %s) RETURNING id",
                (url, score)
            )

            audit_id = cur.fetchone()[0]
            conn.commit()
            conn.close()
            audit_saved = True
        except Exception as db_error:
            import logging
            logging.error(f"Database save failed for url={url}: {db_error}")
            audit_id = None

        return {
            "audit_id": audit_id,
            "audit_saved": audit_saved,
            "score": score,
            "place_id": place.get('place_id'),
            "name": place.get('name'),
            "rating": place.get('rating'),
            "problems": []
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
