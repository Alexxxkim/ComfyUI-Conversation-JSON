import { app } from "../../../scripts/app.js";

const NODE_TYPES = new Set(["DMCanvasConversationJSONV2", "DMCanvasConversationJSONPrefixV2"]);

function restoreLegacyControls(node, savedNode) {
    const values = savedNode?.widgets_values;
    if (!Array.isArray(values) || values.length !== 3) return;
    const legacyInput = savedNode.inputs?.find((slot) => slot.name === "conversation" && slot.widget);
    if (!legacyInput) return;
    const controls = { input_format: values[1], case_index: values[2] };
    for (const widget of node.widgets ?? []) {
        if (Object.hasOwn(controls, widget.name)) widget.value = controls[widget.name];
    }
}

function ensureConversationLabel(node) {
    if (!NODE_TYPES.has(node?.comfyClass) && !NODE_TYPES.has(node?.type)) return;
    const input = node.inputs?.find((slot) => slot.name === "conversation");
    if (!input) return;
    input.label = "conversation";
    input.localized_name = "conversation";
    if (input.widget) {
        const widget = node.widgets?.find((item) => item.name === input.widget.name);
        if (widget) widget.hidden = true;
        delete input.widget;
    }
    node.setDirtyCanvas?.(true, true);
}

app.registerExtension({
    name: "DMCanvas.ConversationInputLabels",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_TYPES.has(nodeData.name)) return;
        const originalConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (...argumentsList) {
            const result = originalConfigure?.apply(this, argumentsList);
            restoreLegacyControls(this, argumentsList[0]);
            ensureConversationLabel(this);
            return result;
        };
    },
    nodeCreated: ensureConversationLabel,
    loadedGraphNode: ensureConversationLabel,
});
