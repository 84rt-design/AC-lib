"""Conversion des modèles 3D vers aperçus légers (glTF + vignette).

Point d'attention §5 du cadrage : FBX/OBJ s'affichent direct ; C4D et STEP
sont propriétaires et exigent une conversion à l'import. C'est le principal
point technique à valider tôt.

Dispatch par extension via `convert()`. Chaque backend renvoie un
`ConversionResult` (glTF, vignette, bbox, polycount).
"""

from aclib.core.conversion.base import ConversionResult, Mesh3DInfo, convert

__all__ = ["ConversionResult", "Mesh3DInfo", "convert"]
