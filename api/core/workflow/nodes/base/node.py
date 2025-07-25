import logging
from abc import abstractmethod
from collections.abc import Generator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Union

from core.workflow.entities.node_entities import NodeRunResult
from core.workflow.entities.workflow_node_execution import WorkflowNodeExecutionStatus
from core.workflow.nodes.base.entities import BaseNodeData, RetryConfig
from core.workflow.nodes.enums import ErrorStrategy, NodeType
from core.workflow.nodes.event import NodeEvent, RunCompletedEvent

if TYPE_CHECKING:
    from core.workflow.graph_engine import Graph, GraphInitParams, GraphRuntimeState
    from core.workflow.graph_engine.entities.event import InNodeEvent

logger = logging.getLogger(__name__)


class BaseNode:
    _node_type: ClassVar[NodeType]

    def __init__(
        self,
        id: str,
        config: Mapping[str, Any],
        graph_init_params: "GraphInitParams",
        graph: "Graph",
        graph_runtime_state: "GraphRuntimeState",
        previous_node_id: Optional[str] = None,
        thread_pool_id: Optional[str] = None,
    ) -> None:
        self.id = id
        self.tenant_id = graph_init_params.tenant_id
        self.app_id = graph_init_params.app_id
        self.workflow_type = graph_init_params.workflow_type
        self.workflow_id = graph_init_params.workflow_id
        self.graph_config = graph_init_params.graph_config
        self.user_id = graph_init_params.user_id
        self.user_from = graph_init_params.user_from
        self.invoke_from = graph_init_params.invoke_from
        self.workflow_call_depth = graph_init_params.call_depth
        self.graph = graph
        self.graph_runtime_state = graph_runtime_state
        self.previous_node_id = previous_node_id
        self.thread_pool_id = thread_pool_id

        node_id = config.get("id")
        if not node_id:
            raise ValueError("Node ID is required.")

        self.node_id = node_id

    @abstractmethod
    def init_node_data(self, data: Mapping[str, Any]) -> None: ...

    @abstractmethod
    def _run(self) -> NodeRunResult | Generator[Union[NodeEvent, "InNodeEvent"], None, None]:
        """
        Run node
        :return:
        """
        raise NotImplementedError

    def run(self) -> Generator[Union[NodeEvent, "InNodeEvent"], None, None]:
        try:
            result = self._run()
        except Exception as e:
            logger.exception(f"Node {self.node_id} failed to run")
            result = NodeRunResult(
                status=WorkflowNodeExecutionStatus.FAILED,
                error=str(e),
                error_type="WorkflowNodeError",
            )

        if isinstance(result, NodeRunResult):
            yield RunCompletedEvent(run_result=result)
        else:
            yield from result

    @classmethod
    def extract_variable_selector_to_variable_mapping(
        cls,
        *,
        graph_config: Mapping[str, Any],
        config: Mapping[str, Any],
    ) -> Mapping[str, Sequence[str]]:
        """Extracts references variable selectors from node configuration.

        The `config` parameter represents the configuration for a specific node type and corresponds
        to the `data` field in the node definition object.

        The returned mapping has the following structure:

            {'1747829548239.#1747829667553.result#': ['1747829667553', 'result']}

        For loop and iteration nodes, the mapping may look like this:

            {
                "1748332301644.input_selector": ["1748332363630", "result"],
                "1748332325079.1748332325079.#sys.workflow_id#": ["sys", "workflow_id"],
            }

        where `1748332301644` is the ID of the loop / iteration node,
        and `1748332325079` is the ID of the node inside the loop or iteration node.

        Here, the key consists of two parts: the current node ID (provided as the `node_id`
        parameter to `_extract_variable_selector_to_variable_mapping`) and the variable selector,
        enclosed in `#` symbols. These two parts are separated by a dot (`.`).

        The value is a list of string representing the variable selector, where the first element is the node ID
        of the referenced variable, and the second element is the variable name within that node.

        The meaning of the above response is:

        The node with ID `1747829548239` references the variable `result` from the node with
        ID `1747829667553`. For example, if `1747829548239` is a LLM node, its prompt may contain a
        reference to the `result` output variable of node `1747829667553`.

        :param graph_config: graph config
        :param config: node config
        :return:
        """
        node_id = config.get("id")
        if not node_id:
            raise ValueError("Node ID is required when extracting variable selector to variable mapping.")

        # Pass raw dict data instead of creating NodeData instance
        data = cls._extract_variable_selector_to_variable_mapping(
            graph_config=graph_config, node_id=node_id, node_data=config.get("data", {})
        )
        return data

    @classmethod
    def _extract_variable_selector_to_variable_mapping(
        cls,
        *,
        graph_config: Mapping[str, Any],
        node_id: str,
        node_data: Mapping[str, Any],
    ) -> Mapping[str, Sequence[str]]:
        return {}

    @classmethod
    def get_default_config(cls, filters: Optional[dict] = None) -> dict:
        return {}

    @property
    def type_(self) -> NodeType:
        return self._node_type

    @classmethod
    @abstractmethod
    def version(cls) -> str:
        """`node_version` returns the version of current node type."""
        # NOTE(QuantumGhost): This should be in sync with `NODE_TYPE_CLASSES_MAPPING`.
        #
        # If you have introduced a new node type, please add it to `NODE_TYPE_CLASSES_MAPPING`
        # in `api/core/workflow/nodes/__init__.py`.
        raise NotImplementedError("subclasses of BaseNode must implement `version` method.")

    @property
    def continue_on_error(self) -> bool:
        return False

    @property
    def retry(self) -> bool:
        return False

    # Abstract methods that subclasses must implement to provide access
    # to BaseNodeData properties in a type-safe way

    @abstractmethod
    def _get_error_strategy(self) -> Optional[ErrorStrategy]:
        """Get the error strategy for this node."""
        ...

    @abstractmethod
    def _get_retry_config(self) -> RetryConfig:
        """Get the retry configuration for this node."""
        ...

    @abstractmethod
    def _get_title(self) -> str:
        """Get the node title."""
        ...

    @abstractmethod
    def _get_description(self) -> Optional[str]:
        """Get the node description."""
        ...

    @abstractmethod
    def _get_default_value_dict(self) -> dict[str, Any]:
        """Get the default values dictionary for this node."""
        ...

    @abstractmethod
    def get_base_node_data(self) -> BaseNodeData:
        """Get the BaseNodeData object for this node."""
        ...

    # Public interface properties that delegate to abstract methods
    @property
    def error_strategy(self) -> Optional[ErrorStrategy]:
        """Get the error strategy for this node."""
        return self._get_error_strategy()

    @property
    def retry_config(self) -> RetryConfig:
        """Get the retry configuration for this node."""
        return self._get_retry_config()

    @property
    def title(self) -> str:
        """Get the node title."""
        return self._get_title()

    @property
    def description(self) -> Optional[str]:
        """Get the node description."""
        return self._get_description()

    @property
    def default_value_dict(self) -> dict[str, Any]:
        """Get the default values dictionary for this node."""
        return self._get_default_value_dict()
