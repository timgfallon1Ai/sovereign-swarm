"""MedicalImagingAnalyzer -- Phase A heuristic / Phase B MedGemma via MLX."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from sovereign_swarm.medical.models import ImagingAnalysis

logger = structlog.get_logger()


class MedicalImagingAnalyzer:
    """Analyze medical images.

    Phase A (current): Heuristic-based analysis descriptions from metadata.
    Phase B (Mac Studio): MedGemma 1.5 via MLX for real image analysis.
    """

    def __init__(self) -> None:
        self._medgemma_available = False
        self._check_medgemma()

    def _check_medgemma(self) -> None:
        """Check if MedGemma MLX weights are available (Phase B)."""
        try:
            import mlx  # noqa: F401

            weights_path = os.environ.get(
                "MEDGEMMA_WEIGHTS",
                str(Path.home() / ".sovereign" / "models" / "medgemma-1.5"),
            )
            if Path(weights_path).exists():
                self._medgemma_available = True
                logger.info(
                    "imaging.medgemma_available", weights=weights_path
                )
            else:
                logger.info("imaging.medgemma_weights_not_found")
        except ImportError:
            logger.info("imaging.mlx_not_installed")

    async def analyze_image(
        self,
        image_path: str,
        modality: str,
        clinical_context: str = "",
    ) -> ImagingAnalysis:
        """Analyze a medical image.

        Routes to MedGemma (Phase B) if available, otherwise returns
        heuristic placeholder analysis.
        """
        if not Path(image_path).exists():
            return ImagingAnalysis(
                modality=modality,
                findings=["Image file not found"],
                impression="Unable to analyze -- image file does not exist.",
                confidence=0.0,
            )

        if self._medgemma_available:
            return await self._medgemma_analysis(
                image_path, modality, clinical_context
            )
        return self._heuristic_analysis(image_path, modality, clinical_context)

    def _heuristic_analysis(
        self,
        image_path: str,
        modality: str,
        clinical_context: str = "",
    ) -> ImagingAnalysis:
        """Phase A: Structured placeholder noting Phase B required for real analysis."""
        file_size = Path(image_path).stat().st_size
        file_ext = Path(image_path).suffix.lower()

        modality_descriptions = {
            "xray": "X-ray radiograph",
            "ct": "CT scan cross-section",
            "mri": "MRI scan",
            "ultrasound": "Ultrasound image",
            "histopath": "Histopathology slide",
        }
        modality_label = modality_descriptions.get(modality, modality)

        findings = [
            f"Image received: {modality_label} ({file_ext}, {file_size:,} bytes)",
            "Heuristic analysis only (Phase A) -- no ML inference performed.",
            "Real diagnostic analysis requires MedGemma 1.5 via MLX (Phase B).",
        ]
        if clinical_context:
            findings.append(f"Clinical context provided: {clinical_context}")

        return ImagingAnalysis(
            modality=modality,
            findings=findings,
            impression=(
                f"Phase A placeholder for {modality_label}. "
                "Deploy MedGemma 1.5 on Mac Studio for real diagnostic inference."
            ),
            confidence=0.0,
            regions_of_interest=[],
        )

    async def _medgemma_analysis(
        self,
        image_path: str,
        modality: str,
        clinical_context: str = "",
    ) -> ImagingAnalysis:
        """Phase B stub: MedGemma 1.5 inference via MLX.

        Will be implemented when Mac Studio + MLX weights are available.
        """
        # TODO: Phase B -- load MedGemma via MLX, run inference
        logger.warning("imaging.medgemma_stub_called")
        return ImagingAnalysis(
            modality=modality,
            findings=[
                "MedGemma inference not yet implemented.",
                "MLX weights detected but inference pipeline pending.",
            ],
            impression="Phase B MedGemma analysis stub -- implementation pending.",
            confidence=0.0,
            regions_of_interest=[],
        )
