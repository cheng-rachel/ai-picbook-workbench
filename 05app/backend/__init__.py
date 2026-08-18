"""Backend data and service layer."""

from .repository import ReferenceRepository
from .context_service import ContextPreparationService, prepare_proposal_context
from .rag_service import LocalRagService
from .services import HistoricalVocabularyService, ReferenceDataService
from .proposal_workflow import ProposalWorkflow, generate_proposals
from .finalization_workflow import FinalizationWorkflow

__all__ = ["ReferenceRepository", "ReferenceDataService", "HistoricalVocabularyService",
           "LocalRagService", "ContextPreparationService", "prepare_proposal_context"]
__all__ += ["ProposalWorkflow", "generate_proposals"]
__all__ += ["FinalizationWorkflow"]
