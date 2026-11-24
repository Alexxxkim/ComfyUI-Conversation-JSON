import { app } from "../../../scripts/app.js";

const socketNames = new Set(["conversation", "region", "style_name", "style_prompt"]);

function labelInputs(node) {
    if ((node.comfyClass ?? node.type) !== "DMCanvasConversationJSONV3") return;
    for (const slot of node.inputs ?? []) {
        if (!socketNames.has(slot.name)) continue;
        slot.label = slot.name;
        slot.localized_name = slot.name;
    }
}

app.registerExtension({
    name: "DMCanvas.ConversationJSONV3.InputLabels",
    nodeCreated: labelInputs,
    loadedGraphNode: labelInputs,
});
