import os
import json
import time
import glob
import traceback
import edge_tts
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# AQUÍ ESTÁN TODOS TUS MOTORES NATIVOS LISTOS PARA TOMAR EL MICRÓFONO
VOCES_TTS = {
    "en": "en-US-ChristopherNeural", 
    "es": "es-MX-JorgeNeural", 
    "ja": "ja-JP-KeitaNeural",
    "fr": "fr-FR-HenriNeural",     
    "pt": "pt-BR-AntonioNeural",   
    "it": "it-IT-DiegoNeural",     
    "de": "de-DE-KillianNeural",
    "zh": "zh-CN-XiaoxiaoNeural"
}
VOZ_POR_DEFECTO = "es-MX-JorgeNeural"
CARPETA_AUDIOS = "audios_guardados"
os.makedirs(CARPETA_AUDIOS, exist_ok=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)

app.mount("/audios", StaticFiles(directory=os.path.join(BASE_DIR, "audios_guardados")), name="audios")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

def obtener_ruta_memoria(nombre, modo):
    n = nombre.strip().lower().replace(" ", "_")
    m = modo.strip().lower().replace(" ", "_").replace("é", "e")
    return f"memoria_{n}_{m}.json"

def cargar_memoria(nombre, modo):
    archivo = obtener_ruta_memoria(nombre, modo)
    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f: return json.load(f)
    return []

def guardar_memoria(nombre, modo, historial):
    with open(obtener_ruta_memoria(nombre, modo), "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=4)

def generar_prompt_modo(nombre, carrera, modo):
    modo_limpio = modo.lower()
    
    # =======================================================
    # MODO 1: VOCABULARIO (Mantenemos tu prompt original intacto)
    # =======================================================
    if "vocabulario" in modo_limpio or "tecnico" in modo_limpio or "técnico" in modo_limpio:
        inst = (
            f"Eres el Tutor de VOXIS para la carrera de '{carrera}'.\n"
            "El usuario te dirá qué idioma quiere practicar.\n"
            "Tu tarea es INVENTAR un término técnico avanzado de esa carrera en el idioma solicitado.\n"
            "OBLIGATORIO: Si es Japonés ('ja') o Chino ('zh'), usa Kanjis/Hanzi nativos en 'palabra_extranjera' y 'ejemplo_extranjero'.\n"
            "Genera la información DIRECTAMENTE en este formato JSON exacto:"
        )
        fmt = (
            "{\n"
            '  "palabra_extranjera": "システム",\n'
            '  "fonetica_espanol": "shi-su-te-mu",\n'
            '  "significado_espanol": "Sistema informático",\n'
            '  "contexto_espanol": "Se usa en tecnología",\n'
            '  "ejemplo_extranjero": "新しいシステムを作ります",\n'
            '  "traduccion_ejemplo": "Hacemos un sistema nuevo",\n'
            '  "codigo_idioma": "ja"\n'
            "}"
        )
        # Retorno normal para Vocabulario
        return f"{inst}\n\nEJEMPLO JSON OBLIGATORIO:\n{fmt}"
    # =======================================================
    # MODO 2: ORATORIA (Corrección Profunda de Gramática y Spanglish)
    # =======================================================
    elif "oratoria" in modo_limpio:
        inst = (
            f"Eres el Entrenador estricto pero amable de Oratoria de VOXIS para alumnos de {carrera}.\n"
            "Misión:\n"
            "1. Pregunta el tema de la exposición y si está listo para empezar.\n"
            "2. Escucha su exposición. Tu charla y explicaciones DEBEN SER EN ESPAÑOL.\n"
            "3. CORRECCIÓN PROFUNDA: No te limites solo a las muletillas. Si el alumno tiene mala gramática, inventa palabras, mezcla idiomas (Spanglish) o dice frases sin sentido, DETENLO y corrígelo constructivamente.\n"
            "4. RECONSTRUCCIÓN: Explícale su error en español, y luego RECONSTRUYE su idea dándole la frase profesional exacta EN EL IDIOMA QUE ESTÁ PRACTICANDO.\n"
            "REGLA DE AUDIO: Tu idioma base es 'es'. Usa otro código (como 'en' o 'fr') estrictamente para CITAR las palabras del alumno y para decir las SUGERENCIAS reconstruidas en bloques separados.\n"
            "REGLA DE FORMATO (CRÍTICA): NUNCA uses comillas dobles (\") dentro de tus respuestas. Usa SIEMPRE comillas simples (' '). Esto es vital para no romper el formato JSON."
        )
        fmt = (
            '{\n'
            '  "respuesta": [\n'
            '    {"lang": "es", "texto": "Noté varias áreas de mejora. Mezclaste español e inglés diciendo "},\n'
            '    {"lang": "en", "texto": "apport y beneficios"},\n'
            '    {"lang": "es", "texto": ". Para sonar profesional en tu tema, deberías reestructurar tu idea completa así: "},\n'
            '    {"lang": "en", "texto": "Technology in medicine is very important because it provides high precision and many benefits"},\n'
            '    {"lang": "es", "texto": ". ¿Te gustaría intentar repetir esta frase?"}\n'
            '  ]\n'
            '}'
        )
        return f"{inst}\n\nFORMATO JSON OBLIGATORIO:\n{fmt}"
   # =======================================================
    # MODO 3: CHARLA CASUAL (Multi-idioma y Traductor Amigable)
    # =======================================================
    else: 
        inst = (
            f"Eres un compañero y amigo de intercambio en VOXIS para alumnos de {carrera}.\n"
            "Misión:\n"
            "1. Mantén una plática casual, relajada y amigable en el idioma que el usuario decida platicar.\n"
            "2. Sé un apoyo: Si el usuario se traba o te pregunta en español cómo se dice algo en otro idioma, respóndele amablemente explicándole en español y dándole la traducción exacta en el idioma que están practicando.\n"
            "REGLA DE AUDIO (VITAL): Tu cerebro debe separar los idiomas. Si hablas en español, usa el código 'es'. Si hablas, traduces o pronuncias algo en otro idioma, usa OBLIGATORIAMENTE un bloque separado con su código respectivo (ej. 'en' para inglés, 'fr' para francés, etc.).\n"
            "REGLA DE FORMATO (CRÍTICA): NUNCA uses comillas dobles (\") dentro de tus respuestas. Usa SIEMPRE comillas simples (' '). Esto es vital para no romper el formato JSON."
        )
        fmt = (
            '{\n'
            '  "respuesta": [\n'
            '    {"lang": "es", "texto": "¡Claro que sí! Para decir eso de forma casual se usa la palabra "},\n'
            '    {"lang": "en", "texto": "awesome"},\n'
            '    {"lang": "es", "texto": ". Por ejemplo, podrías decir que tu proyecto está quedando muy bien. ¿Quieres que sigamos platicando en inglés o en español?"}\n'
            '  ]\n'
            '}'
        )
        return f"{inst}\n\nFORMATO JSON OBLIGATORIO:\n{fmt}"

async def generar_audio(texto, lang, ruta_salida):
    # AQUÍ ES DONDE EDGE TTS ELIGE EL MICRÓFONO SEGÚN EL IDIOMA
    voz = VOCES_TTS.get(lang.lower(), VOZ_POR_DEFECTO)
    comunicador = edge_tts.Communicate(texto, voz)
    await comunicador.save(ruta_salida)

@app.post("/api/iniciar")
async def iniciar_sesion(nombre: str = Form(...), carrera: str = Form(...), modo: str = Form(...)):
    try:
        nombre_limpio = nombre.strip().lower().replace(" ", "_")
        modo_limpio = modo.lower()
        
        prompt_sistema = generar_prompt_modo(nombre, carrera, modo)
        historial = cargar_memoria(nombre, modo)
        historial = [m for m in historial if m.get("role") != "system"]
        historial.insert(0, {"role": "system", "content": prompt_sistema})
        
        if "vocabulario" in modo_limpio or "tecnico" in modo_limpio or "técnico" in modo_limpio:
            msg = f"¡Hola {nombre}! Bienvenido a VOXIS el simulador de vocabulario técnico de {carrera}. ¿En qué idioma introduciremos nuevos términos hoy?"
        elif "oratoria" in modo_limpio:
            msg = f"Saludos bienvenido a VOXIS {nombre}. El panel está listo para tu defensa de {carrera}. ¿En qué idioma será tu presentación?"
        else:
            msg = f"¡Hey {nombre}! Qué bueno verte acá en VOXIS. Vamos a relajarnos un rato con una charla casual. ¿En qué idioma te gustaría platicar hoy?"
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        ruta_audio = f"{CARPETA_AUDIOS}/{nombre_limpio}_{timestamp}_tutor.mp3"
        
        await generar_audio(msg, "es", ruta_audio)
        historial.append({"role": "assistant", "content": msg, "audio": ruta_audio})
        guardar_memoria(nombre, modo, historial)
        
        return {"mensaje": msg, "audio_url": f"/audios/{os.path.basename(ruta_audio)}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/chat")
async def procesar_chat(nombre: str = Form(...), modo: str = Form(...), audio: UploadFile = File(...)):
    try:
        if not GROQ_API_KEY: raise Exception("No se encontró la API Key.")

        nombre_limpio = nombre.strip().lower().replace(" ", "_")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        ruta_audio_usuario = f"{CARPETA_AUDIOS}/{nombre_limpio}_{timestamp}_alumno.webm"
        
        with open(ruta_audio_usuario, "wb") as buffer:
            buffer.write(await audio.read())
            
        cliente_groq = Groq(api_key=GROQ_API_KEY)

        # ==============================================================
        # WHISPER INTELIGENTE: DETECTA MULETILLAS SOLO EN ORATORIA
        # ==============================================================
        if "oratoria" in modo.lower():
            transcripcion = cliente_groq.audio.transcriptions.create(
                file=("audio.webm", open(ruta_audio_usuario, "rb")), 
                model="whisper-large-v3", 
                prompt="ehhh, mmmmm, ahhh, este, bueno, osea, mhm, uh, um, well, you know, euh, alors...", # <-- AHORA ES MULTILINGÜE
                response_format="json"
            ).text
        else:
            transcripcion = cliente_groq.audio.transcriptions.create(
                file=("audio.webm", open(ruta_audio_usuario, "rb")), 
                model="whisper-large-v3", 
                response_format="json"
            ).text
        # ==============================================================
        # ==============================================================

        historial = cargar_memoria(nombre, modo)
        mensajes_api = [{"role": m["role"], "content": m["content"]} for m in historial]
        mensajes_api.append({"role": "user", "content": transcripcion})
        
        respuesta_stream = cliente_groq.chat.completions.create(
            messages=mensajes_api, 
            model="llama-3.3-70b-versatile", 
            response_format={"type": "json_object"}
        )
        
        contenido_bruto = respuesta_stream.choices[0].message.content
        
        try:
            datos_json = json.loads(contenido_bruto)
            bloques = []
            modo_limpio = modo.lower()
            
            if "vocabulario" in modo_limpio or "tecnico" in modo_limpio or "técnico" in modo_limpio:
                p = datos_json.get("palabra_extranjera", "")
                f = datos_json.get("fonetica_espanol", "")
                s = datos_json.get("significado_espanol", "")
                c = datos_json.get("contexto_espanol", "")
                ext = datos_json.get("ejemplo_extranjero", "")
                t = datos_json.get("traduccion_ejemplo", "")
                codigo = datos_json.get("codigo_idioma", "en")
                
                if p and p not in ["null", "None", ""]:
                    # 🎧 AQUÍ SE PASAN EL MICRÓFONO JORGE Y LOS MOTORES NATIVOS
                    bloques.append({"lang": "es", "texto": "¡Excelente! El término es "})
                    bloques.append({"lang": codigo, "texto": p}) # <- Motor nativo lee
                    bloques.append({"lang": "es", "texto": f", y se pronuncia {f}. Su significado es {s}. Además, toma en cuenta este contexto: {c}. Por ejemplo: {t}."})
                    
                    if ext:
                        bloques.append({"lang": codigo, "texto": ext}) # <- Motor nativo lee el ejemplo
                else:
                    bloques.append({"lang": "es", "texto": "Tuve un pequeño cruce de cables. ¿Podrías repetirme el idioma?"})
            
            elif "respuesta" in datos_json:
                for b in datos_json["respuesta"]:
                    bloques.append({"lang": b.get("lang", "es"), "texto": str(b.get("texto", ""))})
            else:
                bloques = [{"lang": "es", "texto": "Formato interno inesperado, intentémoslo de nuevo."}]
                    
        except Exception as e:
            print(f"Error parseando: {e}")
            bloques = [{"lang": "es", "texto": "Tuve un pequeño tropiezo, ¿puedes repetirlo?"}]
            
        texto_ia_completo = ""
        ruta_audio_ia = f"{CARPETA_AUDIOS}/{nombre_limpio}_{timestamp}_tutor.mp3"
        
        with open(ruta_audio_ia, 'wb') as archivo_salida:
            for i, b in enumerate(bloques):
                t = b.get("texto", "")
                l = b.get("lang", "es")
                texto_ia_completo += t + " "
                
                if t.strip():
                    ruta_temp = f"{CARPETA_AUDIOS}/temp_{timestamp}_{i}.mp3"
                    await generar_audio(t, l, ruta_temp)
                    with open(ruta_temp, 'rb') as archivo_temp:
                        archivo_salida.write(archivo_temp.read())
                    os.remove(ruta_temp)
        
        historial.append({"role": "user", "content": transcripcion, "audio": ruta_audio_usuario})
        historial.append({"role": "assistant", "content": texto_ia_completo.strip(), "audio": ruta_audio_ia})
        guardar_memoria(nombre, modo, historial)
        
        return {
            "texto_usuario": transcripcion,
            "texto_ia": texto_ia_completo.strip(),
            "audio_ia_url": f"/audios/{os.path.basename(ruta_audio_ia)}",
            "audio_usuario_url": f"/audios/{os.path.basename(ruta_audio_usuario)}"
        }

    except Exception as e:
        print(traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/admin/usuarios")
async def obtener_usuarios():
    archivos = glob.glob("memoria_*.json")
    nombres = [f.replace('memoria_', '').replace('.json', '').replace('_', ' ').title() for f in archivos]
    return {"usuarios": nombres}

@app.get("/api/admin/historial/{nombre}")
async def obtener_historial_admin(nombre: str):
    nombre_limpio = nombre.strip().lower().replace(" ", "_")
    archivo = f"memoria_{nombre_limpio}.json"
    if os.path.exists(archivo):
        with open(archivo, "r", encoding="utf-8") as f: return {"historial": json.load(f)}
    return {"historial": []}

@app.get("/")
def read_root():
    return FileResponse("index.html")
