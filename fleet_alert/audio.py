import io
import base64
import logging

log = logging.getLogger(__name__)


def gerar_audio_base64(texto: str) -> str | None:
    """
    Converte texto em áudio TTS (português BR).
    Retorna base64 do arquivo OGG Opus (formato PTT do WhatsApp).
    Retorna None se gTTS não estiver instalado ou falhar.
    """
    try:
        from gtts import gTTS
    except ImportError:
        log.warning("gTTS não instalado — áudio desativado. Execute: pip install gtts")
        return None

    try:
        tts = gTTS(text=texto, lang="pt-br", slow=False)
        mp3_buf = io.BytesIO()
        tts.write_to_fp(mp3_buf)
        mp3_buf.seek(0)
        mp3_bytes = mp3_buf.read()
    except Exception as e:
        log.error("Falha ao gerar TTS: %s", e)
        return None

    ogg_bytes = _converter_para_ogg(mp3_bytes)
    dados = ogg_bytes if ogg_bytes else mp3_bytes

    return base64.b64encode(dados).decode()


def _converter_para_ogg(mp3_bytes: bytes) -> bytes | None:
    """Converte MP3 → OGG Opus via pydub + ffmpeg."""
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        buf = io.BytesIO()
        seg.export(buf, format="ogg", codec="libopus")
        buf.seek(0)
        return buf.read()
    except Exception as e:
        log.warning("Conversão OGG falhou (%s) — enviando MP3", e)
        return None
