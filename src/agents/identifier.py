"""Vision agent responsible for identifying a Pokémon TCG card from an image."""

import base64
import json
import sys
from pathlib import Path
from typing import Union

import anthropic

from src.models.card import CardIdentity

MODEL = "claude-haiku-4-5-20251001"

MEDIA_TYPES: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

SYSTEM_PROMPT = """Tu es un expert en identification de cartes Pokémon TCG.
Analyse l'image de cette carte et extrais les informations suivantes.
Réponds UNIQUEMENT en JSON valide, aucun texte autour.

RÈGLES CRITIQUES POUR LE NUMÉRO DE CARTE :
Le numéro se trouve en BAS À DROITE de la carte, souvent en petit.
C'est l'information LA PLUS IMPORTANTE à lire correctement.

Formats possibles (du plus courant au plus rare) :
- Standard : X/Y (ex: "2/102", "26/106", "049/198")
  X = numéro de la carte, Y = total du set
- Secret Rare : X/Y où X > Y (ex: "101/100", "163/151")
  La carte dépasse le numéro officiel du set
- Numéro seul : juste un nombre, parfois avec zéros (ex: "009", "011")
  Fréquent sur les anciennes cartes japonaises et certaines promos
- Avec préfixe "No." : (ex: "No.151")
  Courant sur les vieilles cartes japonaises
- Sous-set : préfixe + numéro/total (ex: "GG17/GG70", "TG01/TG30")
- Promo avec préfixe d'ère : (ex: "SWSH123", "SM103", "XY75")
- Promo japonaise : numéro/ère-P (ex: "005/SV-P")

INSTRUCTIONS DE LECTURE :
- Lis CHAQUE CHIFFRE un par un, ne devine jamais
- Conserve les zéros devant s'ils sont imprimés ("009" pas "9")
- Conserve le format exact tel qu'imprimé
- Le "/" sépare le numéro de la carte du total du set
- Attention à ne pas confondre avec les HP ou les dégâts d'attaque
  qui sont aussi des chiffres sur la carte
- Si le numéro est partiellement caché, flou, ou illisible,
  indique "number_uncertain": true et baisse la confidence

RÈGLES POUR LA LANGUE :
Détecte la langue par les MOTS imprimés sur la carte, pas par le nom :
- "Faiblesse" / "Résistance" / "Retraite" → FR
- "Weakness" / "Resistance" / "Retreat" → EN
- "よわい" / "ていこう" / "にげる" → JP
- "Schwäche" / "Resistenz" / "Rückzug" → DE
- "Debolezza" / "Resistenza" / "Ritirata" → IT
- "Debilidad" / "Resistencia" / "Retirada" → ES
- "약점" / "저항력" / "후퇴" → KO

RÈGLES POUR LA RARETÉ :
Le symbole de rareté est en bas à droite, près du numéro :
- Cercle noir (●) → Common
- Losange noir (◆) → Uncommon
- Étoile noire (★) → Rare
- Étoile noire holographique → Rare Holo
- Double étoile (★★) → Double Rare
- Étoile blanche ou dorée → Ultra Rare / Secret Rare
- Étoile noire avec "PROMO" → Promo

FORMAT DE RÉPONSE JSON :
{
  "name": "nom du Pokémon tel qu'imprimé",
  "number": "numéro exact tel qu'imprimé (ex: 2/102 ou 009)",
  "language": "FR|EN|JP|DE|IT|ES|KO|PT",
  "set_name": "nom du set si visible, sinon null",
  "set_code": "code du set si connu, sinon null",
  "rarity": "type de rareté détecté",
  "number_uncertain": false,
  "confidence": 0.95
}"""

USER_PROMPT = "Analyse cette carte Pokémon TCG."


class CardIdentifierAgent:
    """Uses Claude's vision capabilities to extract card identity from a photo.

    Given a raw image of a Pokémon TCG card, this agent prompts Claude to
    identify the card name, collector number, language, and set name, then
    returns a structured CardIdentity object.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the agent with an Anthropic API key.

        Args:
            api_key: Anthropic API key used to authenticate vision requests.
        """
        self.api_key = api_key
        self._client: anthropic.Anthropic | None = None

    def _build_client(self) -> anthropic.Anthropic:
        """Lazily initialise and return the Anthropic client."""
        if self._client is None:
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def identify(self, front_image_path: str) -> CardIdentity:
        """Analyse a card front image and return its identity.

        Identification is performed exclusively on the recto — the front face
        carries all the information needed (name, number, language, set).

        Args:
            front_image_path: Filesystem path to the front card image (JPEG, PNG, or WEBP).

        Returns:
            A CardIdentity populated with the extracted fields.

        Raises:
            FileNotFoundError: If front_image_path does not exist.
            ValueError: If the file format is unsupported or the model response
                cannot be parsed.
            anthropic.APIError: On Anthropic API failures.
        """
        path = Path(front_image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        image_data, media_type = self._load_image_as_base64(path)
        client = self._build_client()

        message = client.messages.create(
            model=MODEL,
            max_tokens=768,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {"type": "text", "text": USER_PROMPT},
                    ],
                }
            ],
        )

        raw_text = message.content[0].text
        return self._parse_response(raw_text)

    def _load_image_as_base64(self, image_path: Path) -> tuple[str, str]:
        """Read an image file and return (base64_data, media_type).

        Args:
            image_path: Path to the image file.

        Returns:
            Tuple of (base64-encoded image string, MIME type string).

        Raises:
            ValueError: If the file extension is not supported.
        """
        ext = image_path.suffix.lower()
        media_type = MEDIA_TYPES.get(ext)
        if media_type is None:
            raise ValueError(
                f"Unsupported image format '{ext}'. Supported: {list(MEDIA_TYPES)}"
            )
        image_data = base64.standard_b64encode(image_path.read_bytes()).decode("utf-8")
        return image_data, media_type

    def _parse_response(self, raw_response: str) -> CardIdentity:
        """Parse the model's JSON response into a CardIdentity.

        Args:
            raw_response: Raw text content from the Claude API response.

        Returns:
            A CardIdentity with parsed fields.

        Raises:
            ValueError: If the response is not valid JSON or required fields
                (name, number, language, set_name) are missing.
        """
        text = raw_response.strip()
        # Some models wrap JSON in markdown code fences — strip them
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip().rstrip("`").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Model returned non-JSON response: {raw_response!r}"
            ) from exc

        missing = [f for f in ("name", "number", "language") if not data.get(f)]
        if missing:
            raise ValueError(f"Required fields missing or null in response: {missing}")

        if data.get("number_uncertain"):
            print(
                f"[identifier] number_uncertain=true for '{data.get('number')}' "
                f"(confidence={data.get('confidence')})",
                file=sys.stderr,
            )

        return CardIdentity(
            name=data["name"],
            number=data["number"],
            language=data["language"],
            set_name=data.get("set_name") or "",
            set_code=data.get("set_code"),
            rarity=data.get("rarity"),
        )


if __name__ == "__main__":
    import argparse
    import os

    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(
        prog="python -m src.agents.identifier",
        description="Identify a Pokémon TCG card from a photo using Claude vision.",
    )
    parser.add_argument("--front", required=True, metavar="PATH",
                        help="Path to the front (recto) card image — required.")
    parser.add_argument("--back", default=None, metavar="PATH",
                        help="Path to the back (verso) card image — optional.")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set in environment or .env file")
        sys.exit(1)

    agent = CardIdentifierAgent(api_key=api_key)
    try:
        identity = agent.identify(front_image_path=args.front)
        print(json.dumps(
            {
                "name": identity.name,
                "number": identity.number,
                "language": identity.language,
                "set_name": identity.set_name,
                "set_code": identity.set_code,
                "rarity": identity.rarity,
            },
            indent=2,
            ensure_ascii=False,
        ))
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)
