import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { createContext, SourceTextModule, SyntheticModule } from "node:vm";

async function loadExtension() {
    let extension;
    const context = createContext({});
    const appModule = new SyntheticModule(["app"], function () {
        this.setExport("app", {
            registerExtension(value) {
                extension = value;
            },
        });
    }, { context });
    const source = await readFile(new URL("../web/conversation_input_labels.js", import.meta.url), "utf8");
    const module = new SourceTextModule(source, { context });
    await module.link((specifier) => {
        assert.equal(specifier, "../../../scripts/app.js");
        return appModule;
    });
    await module.evaluate();
    return extension;
}

test("new conversation sockets have an explicit visible label", async () => {
    const extension = await loadExtension();
    const input = { name: "conversation", type: "STRING", link: 5 };
    const node = { comfyClass: "DMCanvasConversationJSONV2", inputs: [input] };
    extension.nodeCreated(node);
    assert.equal(input.label, "conversation");
    assert.equal(input.localized_name, "conversation");
    assert.equal(input.link, 5);
});

test("V2 sockets and configure handlers use the same label repair", async () => {
    const extension = await loadExtension();
    const input = { name: "conversation", type: "STRING", link: 9 };
    const node = { comfyClass: "DMCanvasConversationJSONPrefixV2", inputs: [input] };
    extension.nodeCreated(node);
    assert.equal(input.label, "conversation");
    assert.equal(input.localized_name, "conversation");
    assert.equal(input.link, 9);
    class PrefixNode {
        constructor() {
            this.type = "DMCanvasConversationJSONPrefixV2";
            this.inputs = [{ name: "conversation", widget: { name: "conversation" }, link: 7 }];
        }
    }
    extension.beforeRegisterNodeDef(PrefixNode, { name: "DMCanvasConversationJSONPrefixV2" });
    const configured = new PrefixNode();
    configured.onConfigure({ widgets_values: ["auto", 1] });
    assert.equal(configured.inputs[0].label, "conversation");
    assert.equal(configured.inputs[0].widget, undefined);
    assert.equal(configured.inputs[0].link, 7);
});

test("legacy widget sockets retain their text and connection when relabeled", async () => {
    const extension = await loadExtension();
    const widget = { name: "conversation", value: "user: [1] 画猫" };
    const region = { name: "region", type: "STRING", link: 1 };
    const input = {
        name: "conversation", label: "", type: "STRING", link: 5,
        widget: { name: "conversation" },
    };
    const node = { type: "DMCanvasConversationJSONV2", inputs: [region, input], widgets: [widget] };
    extension.loadedGraphNode(node);
    assert.equal(input.label, "conversation");
    assert.equal(input.widget, undefined);
    assert.equal(input.link, 5);
    assert.equal(widget.value, "user: [1] 画猫");
    assert.equal(widget.hidden, true);
    assert.deepEqual(region, { name: "region", type: "STRING", link: 1 });
});

test("configured saved nodes are fixed after existing configure handlers", async () => {
    const extension = await loadExtension();
    let configuredValue;
    class ConversationNode {
        constructor() {
            this.type = "DMCanvasConversationJSONV2";
            this.inputs = [];
        }

        onConfigure(value) {
            configuredValue = value;
            this.inputs = [{ name: "conversation", widget: { name: "conversation" } }];
            return "configured";
        }
    }
    extension.beforeRegisterNodeDef(ConversationNode, { name: "DMCanvasConversationJSONV2" });
    const node = new ConversationNode();
    assert.equal(node.onConfigure("saved workflow"), "configured");
    assert.equal(configuredValue, "saved workflow");
    assert.equal(node.inputs[0].label, "conversation");
    assert.equal(node.inputs[0].widget, undefined);
});

test("other node types and their handlers remain untouched", async () => {
    const extension = await loadExtension();
    const input = { name: "conversation", widget: { name: "conversation" } };
    const node = { type: "OtherNode", inputs: [input] };
    extension.nodeCreated(node);
    assert.equal(input.label, undefined);
    assert.deepEqual(input.widget, { name: "conversation" });
    class OtherNode {}
    extension.beforeRegisterNodeDef(OtherNode, { name: "OtherNode" });
    assert.equal(OtherNode.prototype.onConfigure, undefined);
});

test("legacy positional widget values preserve the selected case and format", async () => {
    const extension = await loadExtension();
    class ConversationNode {
        constructor() {
            this.type = "DMCanvasConversationJSONV2";
            this.inputs = [{ name: "conversation", type: "STRING", link: 5 }];
            this.widgets = [
                { name: "input_format", value: "auto" },
                { name: "case_index", value: NaN },
            ];
        }
    }
    extension.beforeRegisterNodeDef(ConversationNode, { name: "DMCanvasConversationJSONV2" });
    const node = new ConversationNode();
    node.onConfigure({
        inputs: [{ name: "conversation", widget: { name: "conversation" }, link: 5 }],
        widgets_values: ["auto", "full", 955],
    });
    assert.equal(node.widgets[0].value, "full");
    assert.equal(node.widgets[1].value, 955);
    assert.equal(node.inputs[0].link, 5);
});

test("current two-widget workflows do not have their controls rewritten", async () => {
    const extension = await loadExtension();
    class ConversationNode {
        constructor() {
            this.type = "DMCanvasConversationJSONV2";
            this.inputs = [{ name: "conversation" }];
            this.widgets = [{ name: "input_format", value: "simple" }, { name: "case_index", value: 1 }];
        }
    }
    extension.beforeRegisterNodeDef(ConversationNode, { name: "DMCanvasConversationJSONV2" });
    const node = new ConversationNode();
    node.onConfigure({ inputs: [{ name: "conversation" }], widgets_values: ["simple", 1] });
    assert.equal(node.widgets[0].value, "simple");
    assert.equal(node.widgets[1].value, 1);
});
