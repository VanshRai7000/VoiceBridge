from flask import Flask, request, render_template, send_file, jsonify
from gtts import gTTS
import speech_recognition as sr
import os
from werkzeug.utils import secure_filename
from googletrans import Translator
from pydub import AudioSegment
import uuid
import time

# Add ffmpeg to PATH (needed for pydub)
os.environ["PATH"] += os.pathsep + r"C:\ProgramData\chocolatey\bin"

app = Flask(__name__)

# Configuration for uploads
UPLOAD_FOLDER = 'uploads/'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

translator = Translator()

# ✅ Safer translation (skips transliteration issues)
def safe_translate(text, target_lang="en", retries=3):
    if not text or text.strip() == "":
        return text, None, None

    for attempt in range(retries):
        try:
            detected = translator.detect(text).lang

            # 🚩 Skip translation if already in target language
            if detected == target_lang:
                return text, detected, None

            result = translator.translate(text, src=detected, dest=target_lang)
            translated_text = result.text
            romanized_text = result.pronunciation

            return translated_text, detected, romanized_text
        except Exception as e:
            print(f"Translation attempt {attempt+1} failed: {e}")
            time.sleep(1)

    return text, None, None


@app.route('/')
def index():
    return render_template('index.html')


# ==================== TEXT ➝ VOICE ====================
@app.route('/text-to-voice', methods=['POST'])
def text_to_voice():
    input_text = request.form.get('text', '').strip()
    target_lang = request.form.get('language', 'en')

    if not input_text:
        return jsonify({"error": "Text input cannot be empty."}), 400
    if len(input_text) > 5000:
        return jsonify({"error": "Text input exceeds the character limit."}), 400

    # ✅ Translate before TTS
    translated_text, detected_lang, romanized_text = safe_translate(input_text, target_lang)

    try:
        tts = gTTS(translated_text, lang=target_lang)
        audio_file = os.path.join(app.config['UPLOAD_FOLDER'], f'output_{uuid.uuid4().hex}.mp3')
        tts.save(audio_file)

        return send_file(
            audio_file,
            as_attachment=True,
            download_name="output.mp3"
        )
    except Exception as e:
        return jsonify({"error": f"Text-to-speech conversion failed: {e}"}), 500


# ==================== VOICE ➝ TEXT ====================
def convert_audio(input_file, output_format="wav"):
    try:
        sound = AudioSegment.from_file(input_file)
        base, _ = os.path.splitext(input_file)
        output_file = f"{base}.{output_format}"
        sound.export(output_file, format=output_format)
        return output_file
    except Exception as e:
        raise Exception(f"Audio conversion failed: {e}")

# Point pydub to ffmpeg
AudioSegment.converter = r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"


@app.route('/voice-to-text', methods=['POST'])
def voice_to_text():
    if 'audio' not in request.files or request.files['audio'].filename == '':
        return jsonify({"error": "No audio file uploaded."}), 400

    file = request.files['audio']
    if not file.filename.endswith(('.wav', '.mp3')):
        return jsonify({"error": "Invalid file type. Please upload a .wav or .mp3 file."}), 400

    target_lang = request.form.get('language', 'en')

    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        original_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{uuid.uuid4().hex}_{filename}')
        file.save(original_file_path)

        # Convert MP3 → WAV if needed
        if original_file_path.endswith('.mp3'):
            file_to_process = convert_audio(original_file_path)
        else:
            file_to_process = original_file_path

        # Recognize speech
        recognizer = sr.Recognizer()
        with sr.AudioFile(file_to_process) as source:
            audio = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio, language=target_lang)
        except sr.UnknownValueError:
            return jsonify({"error": "Could not understand the audio."}), 400
        except sr.RequestError as e:
            return jsonify({"error": f"Speech recognition API error: {e}"}), 500

        # ✅ Translate recognized text
        translated_text, detected_lang, romanized_text = safe_translate(text, target_lang)

        response = {
            "status": "success",
            "original_text": text,
            "translated_text": translated_text,
            "romanized_text": romanized_text,
            "detected_language": detected_lang or "unknown",
            "target_language": target_lang,
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": f"Voice-to-text conversion failed: {e}"}), 500

    finally:
        if os.path.exists(original_file_path):
            try:
                os.remove(original_file_path)
            except Exception as cleanup_error:
                print(f"Failed to delete file {original_file_path}: {cleanup_error}")


if __name__ == "__main__":
    app.run(debug=True)
