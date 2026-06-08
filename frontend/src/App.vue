<script setup>
import {
  AlertCircle,
  Atom,
  Beaker,
  Bot,
  BrainCircuit,
  CircleDot,
  Database,
  Dna,
  FileText,
  FileSpreadsheet,
  FlaskConical,
  Loader2,
  Network,
  Paperclip,
  PencilLine,
  Pill,
  Plus,
  Search,
  Send,
  Shield,
  Trash2,
  UploadCloud,
  X
} from "@lucide/vue";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  analyzeOmicsFile,
  createExperimentDataset,
  deleteExperimentDataset,
  getGraphRelationships,
  listExperimentDatasets,
  searchGraphNodes,
  streamAgentChat,
  updateExperimentDataset
} from "./api/client";

const STORAGE_KEY = "mogap.datasets.v1";
const LEGACY_CHAT_STORAGE_KEY = "mogap.chat.sessions.v1";
const CHAT_STORAGE_KEY = "mogap.chat.sessions.v2";

const modules = [
  { id: "chat", label: "多组学机制问答智能体", icon: Bot },
  { id: "graph", label: "知识图谱探索", icon: Network },
  { id: "datasets", label: "实验数据解析", icon: Database }
];

const activeModule = ref("chat");
const initialChatSessionId = createSessionId();
const activeChatSessionId = ref(initialChatSessionId);
const chatSessions = ref([]);
const chatMessagesBySession = ref({
  [initialChatSessionId]: [createWelcomeMessage()]
});
const input = ref("");
const isSending = ref(false);
const pageEnteredAt = Date.now();
const uploadMenuOpen = ref(false);
const datasetPickerOpen = ref(false);
const attachedDataset = ref(null);
const chatDatasetLoadState = ref("idle");
const messagesEnd = ref(null);
const chatThread = ref(null);
const chatFileInput = ref(null);

const messages = computed({
  get() {
    return ensureSessionMessages(activeChatSessionId.value);
  },
  set(value) {
    chatMessagesBySession.value[activeChatSessionId.value] = value;
    saveChatSessions();
  }
});

const datasets = ref([]);
const datasetFileInput = ref(null);
const selectedDatasetFile = ref(null);
const datasetDisplayName = ref("");
const datasetTopK = ref(100);
const datasetStatus = ref({ type: "idle", message: "" });
const isParsingDataset = ref(false);
const datasetStorageMode = ref("local");
const previewDatasetId = ref(null);
const datasetPreviewOpen = ref(false);
const activeDatasetPreviewGroupId = ref("");
const editingDatasetId = ref(null);
const editingDatasetName = ref("");

const graphQuery = ref("");
const graphDepth = ref(2);
const graphVectorSearch = ref(true);
const graphRerank = ref(true);
const graphLimit = 200;
const graphStatus = ref("ready");
const graphData = ref({ nodes: [], relationships: [], warnings: [] });
const graphAnchors = ref([]);
const graphAnchorResults = ref({});
const graphExpansionResults = ref({});
const graphVisibleNodeIds = ref(new Set());
const graphEnteringNodeIds = ref(new Set());
const graphNodePositions = ref({});
const graphRevealTimers = [];
const graphCanvasStageRef = ref(null);
const graphCanvasRef = ref(null);
const graphMinimapCanvasRef = ref(null);
const graphScene = ref({ width: 1600, height: 900, nodes: [], relationships: [], state: "Idle" });
const graphViewport = ref({ x: 0, y: 0, scale: 1 });
const graphDragState = ref(null);
const isGraphDragging = ref(false);
const isGraphMinimapDragging = ref(false);
const hoveredGraphItem = ref(null);
const selectedGraphItem = ref(null);
const graphTooltip = ref(null);
const GRAPH_NODE_LONG_PRESS_MS = 100;
const GRAPH_NODE_LONG_PRESS_MOVE_TOLERANCE = 9;
const GRAPH_CORE_DISTANCE = 520;
const GRAPH_CORE_FIRST_HOP_RATIO = 0.3;
const GRAPH_CORE_HOP_RATIO_STEP = 0.1;
const CHAT_SCROLL_BOTTOM_PADDING = 4;
let graphAnimationFrame = 0;
let graphAnimationStartedAt = 0;
let graphSpringFrame = 0;
let graphLastSpringAt = 0;
let graphResizeObserver = null;
let graphNodeLongPressTimer = 0;
let graphClickSuppressTimer = 0;
let suppressNextGraphClick = false;

const pageTitle = computed(() => modules.find((item) => item.id === activeModule.value)?.label || "多组学机制问答智能体");
const savedDatasets = computed(() => datasets.value);
const activeChatSession = computed(() => chatSessions.value.find((session) => session.id === activeChatSessionId.value) || null);
const activeSessionDataset = computed(() => activeChatSession.value?.loadedDataset || null);
const isComposerLocked = computed(() => isSending.value || chatDatasetLoadState.value === "loading");
const previewDataset = computed(() => datasets.value.find((dataset) => dataset.id === previewDatasetId.value) || null);
const previewDatasetGroups = computed(() => getDatasetPreviewGroups(previewDataset.value));
const activeDatasetPreviewGroup = computed(() => {
  const groups = previewDatasetGroups.value;
  return groups.find((group) => group.id === activeDatasetPreviewGroupId.value) || groups.find((group) => group.rows.length) || groups[0] || null;
});
const graphNodes = computed(() => graphData.value.nodes || []);
const graphRelationships = computed(() => graphData.value.relationships || []);
const graphDetailItem = computed(() => hoveredGraphItem.value || selectedGraphItem.value);
const graphAnchorIds = computed(() => new Set(graphAnchors.value.map((anchor) => anchor.id)));
const graphBridgeRelationshipIds = computed(() => findBridgeRelationshipIds(graphAnchors.value, graphRelationships.value));
const graphEntityTypes = computed(() => [...new Set(graphNodes.value.map((node) => getNodeType(node)))].slice(0, 8));
const graphStats = computed(() => ({
  nodes: graphNodes.value.length,
  relationships: graphRelationships.value.length,
  hop: graphDepth.value,
  limit: graphLimit,
  layout: graphAnchors.value.length > 1 ? "Dual Core" : "Single Core"
}));

const entityColors = {
  Gene: "#3B82F6",
  Protein: "#10B981",
  Metabolite: "#F59E0B",
  Lipid: "#EC4899",
  Pathway: "#8B5CF6",
  Disease: "#EF4444",
  Drug: "#06B6D4",
  Phenotype: "#84CC16",
  Experiment: "#F97316",
  Publication: "#94A3B8"
};

onMounted(() => {
  loadDatasets();
  loadChatSessions();
  setupGraphCanvas();
});

onBeforeUnmount(() => {
  clearGraphRevealTimers();
  clearGraphNodeLongPressTimer();
  clearGraphClickSuppressTimer();
  cancelAnimationFrame(graphAnimationFrame);
  cancelAnimationFrame(graphSpringFrame);
  graphResizeObserver?.disconnect();
});

watch([graphViewport, hoveredGraphItem, selectedGraphItem], () => {
  drawGraphScene();
  drawGraphMinimap();
}, { deep: true });

watch(activeModule, async (moduleId) => {
  if (moduleId !== "graph") {
    return;
  }
  await nextTick();
  setupGraphCanvas();
  if (graphNodes.value.length) {
    rebuildGraphScene(new Set(graphNodes.value.map((node) => node.id)), graphScene.value.state || "SingleCoreLayout");
  }
});

function setModule(moduleId) {
  activeModule.value = moduleId;
  uploadMenuOpen.value = false;
  datasetPickerOpen.value = false;
}

function startNewChat() {
  activeModule.value = "chat";
  const sessionId = createSessionId();
  activeChatSessionId.value = sessionId;
  chatMessagesBySession.value[sessionId] = [createWelcomeMessage()];
  input.value = "";
  attachedDataset.value = null;
  chatDatasetLoadState.value = "idle";
  uploadMenuOpen.value = false;
  datasetPickerOpen.value = false;
  nextTick(scrollToBottom);
}

function openChatSession(sessionId) {
  activeModule.value = "chat";
  activeChatSessionId.value = sessionId;
  ensureSessionMessages(sessionId);
  attachedDataset.value = null;
  chatDatasetLoadState.value = "idle";
  uploadMenuOpen.value = false;
  datasetPickerOpen.value = false;
  saveChatSessions();
  nextTick(scrollToBottom);
}

function ensureSessionMessages(sessionId) {
  if (!chatMessagesBySession.value[sessionId]) {
    chatMessagesBySession.value[sessionId] = [createWelcomeMessage()];
  }
  return chatMessagesBySession.value[sessionId];
}

function setSessionMessages(sessionId, nextMessages) {
  chatMessagesBySession.value = {
    ...chatMessagesBySession.value,
    [sessionId]: nextMessages
  };
}

function appendSessionMessage(sessionId, message) {
  const nextMessages = [...ensureSessionMessages(sessionId), message];
  setSessionMessages(sessionId, nextMessages);
  return nextMessages.length - 1;
}

function updateSessionMessage(sessionId, index, patcher) {
  const currentMessages = ensureSessionMessages(sessionId);
  if (!currentMessages[index]) {
    return null;
  }
  const currentMessage = currentMessages[index];
  const patch = typeof patcher === "function" ? patcher(currentMessage) : patcher;
  const nextMessage = { ...currentMessage, ...patch };
  const nextMessages = currentMessages.map((message, messageIndex) => (messageIndex === index ? nextMessage : message));
  setSessionMessages(sessionId, nextMessages);
  return nextMessage;
}

function loadChatSessions() {
  localStorage.removeItem(LEGACY_CHAT_STORAGE_KEY);
  try {
    const saved = JSON.parse(localStorage.getItem(CHAT_STORAGE_KEY) || "null");
    if (saved?.sessions?.length && saved?.messagesBySession) {
      chatSessions.value = saved.sessions.map(normalizeChatSession);
      chatMessagesBySession.value = {
        ...saved.messagesBySession,
        [activeChatSessionId.value]: [createWelcomeMessage()]
      };
    }
    ensureSessionMessages(activeChatSessionId.value);
  } catch {
    localStorage.removeItem(CHAT_STORAGE_KEY);
  }
}

function saveChatSessions() {
  const visibleSessionIds = new Set(chatSessions.value.map((session) => session.id));
  const persistedMessages = Object.fromEntries(
    Object.entries(chatMessagesBySession.value).filter(([sessionId]) => visibleSessionIds.has(sessionId))
  );
  localStorage.setItem(
    CHAT_STORAGE_KEY,
    JSON.stringify({
      activeSessionId: activeChatSessionId.value,
      sessions: chatSessions.value,
      messagesBySession: persistedMessages
    })
  );
}

function createSessionId() {
  return `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createWelcomeMessage() {
  return {
    id: Date.now(),
    role: "assistant",
    content: "你好，我是多组学机制问答智能体。你可以直接提问基因、通路、表型或实验结果相关问题，也可以附加已解析实验数据一起分析。"
  };
}

function normalizeChatSession(session) {
  const fallbackTime = new Date().toISOString();
  return {
    ...session,
    createdAt: session.createdAt || session.updatedAt || fallbackTime
  };
}

function ensureChatSessionRecord(sessionId, query) {
  let session = chatSessions.value.find((item) => item.id === sessionId);
  if (!session) {
    const now = new Date().toISOString();
    session = {
      id: sessionId,
      title: query.slice(0, 18) || "新会话",
      createdAt: now
    };
    chatSessions.value.unshift(session);
  }
  return session;
}

function formatSessionTime(session) {
  const createdAt = new Date(session.createdAt || Date.now()).getTime();
  const elapsedSeconds = Math.max(0, Math.floor((pageEnteredAt - createdAt) / 1000));
  if (elapsedSeconds < 60) {
    return "最近";
  }
  const elapsedMinutes = Math.floor(elapsedSeconds / 60);
  if (elapsedMinutes < 60) {
    return `${elapsedMinutes}m`;
  }
  const elapsedHours = Math.floor(elapsedMinutes / 60);
  if (elapsedHours < 24) {
    return `${elapsedHours}h`;
  }
  const elapsedDays = Math.floor(elapsedHours / 24);
  if (elapsedDays < 30) {
    return `${elapsedDays}d`;
  }
  return `${Math.floor(elapsedDays / 30)}months`;
}

function markSessionDatasetLoaded(sessionId, dataset) {
  const session = ensureChatSessionRecord(sessionId, "");
  session.loadedDataset = dataset
    ? {
        id: dataset.id,
        name: dataset.name,
        meta: dataset.meta
      }
    : null;
  saveChatSessions();
}

function renderMarkdown(content) {
  return DOMPurify.sanitize(marked.parse(content || "", { breaks: true }));
}

function selectDataset(dataset) {
  const displayName = getDatasetDisplayName(dataset);
  attachedDataset.value = {
    id: dataset.id,
    type: "existing",
    name: displayName,
    meta: `${dataset.resultCount} 个比较结果 · TOPK ${dataset.topK}`
  };
  datasetPickerOpen.value = false;
  uploadMenuOpen.value = false;
}

function openChatFilePicker() {
  uploadMenuOpen.value = false;
  datasetPickerOpen.value = false;
  chatFileInput.value?.click();
}

async function handleChatFile(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  chatDatasetLoadState.value = "loading";
  try {
    const parsedDataset = await parseAndSaveDataset(file, 100);
    if (parsedDataset) {
      selectDataset(parsedDataset);
      chatDatasetLoadState.value = "done";
      window.setTimeout(() => {
        if (chatDatasetLoadState.value === "done") {
          chatDatasetLoadState.value = "idle";
        }
      }, 1800);
    } else {
      chatDatasetLoadState.value = "idle";
    }
  } catch {
    chatDatasetLoadState.value = "idle";
  } finally {
    event.target.value = "";
  }
}

function removeAttachment() {
  attachedDataset.value = null;
}

async function sendMessage() {
  const query = input.value.trim();
  if (!query || isComposerLocked.value) {
    return;
  }

  const sessionId = activeChatSessionId.value;
  const activeSession = ensureChatSessionRecord(sessionId, query);

  appendSessionMessage(sessionId, {
    id: Date.now(),
    role: "user",
    content: query,
    attachment: attachedDataset.value ? { ...attachedDataset.value } : null
  });
  if (activeSession && activeSession.title === "新会话") {
    activeSession.title = query.slice(0, 18);
  }
  input.value = "";
  uploadMenuOpen.value = false;
  datasetPickerOpen.value = false;
  isSending.value = true;
  saveChatSessions();
  await scrollToBottom();

  let assistantIndex = -1;
  try {
    const selectedDataset = findAttachedDataset();
    const agentQuery = buildAgentQuery(query, selectedDataset);
    const datasetForRequest = attachedDataset.value && selectedDataset
      ? {
          id: attachedDataset.value.id,
          name: attachedDataset.value.name,
          meta: attachedDataset.value.meta
        }
      : null;
    assistantIndex = appendSessionMessage(sessionId, {
      id: Date.now() + 1,
      role: "assistant",
      content: "",
      status: "thinking"
    });
    if (activeChatSessionId.value === sessionId) {
      await scrollToBottom();
    }

    await streamAgentChat({
      query: agentQuery,
      inputs: datasetForRequest
        ? {
            dataset: {
              id: datasetForRequest.id,
              name: datasetForRequest.name,
              file_name: selectedDataset?.fileName || selectedDataset?.name || "",
              type: attachedDataset.value.type,
              included_in_query: Boolean(selectedDataset)
            }
          }
        : {},
      conversation_id: activeSession?.conversationId || null,
      parent_message_id: activeSession?.parentMessageId || null
    }, async (event) => {
      if (event.event === "error") {
        throw new Error(event.message || "FastAGI streaming error");
      }
      if (activeSession && event.conversation_id) {
        activeSession.conversationId = event.conversation_id;
      }
      if (activeSession && event.message_id) {
        activeSession.parentMessageId = event.message_id;
      }
      if (event.answer) {
        updateSessionMessage(sessionId, assistantIndex, (message) => ({
          status: "streaming",
          content: String(message.content || "") + event.answer
        }));
        if (activeChatSessionId.value === sessionId) {
          await scrollToBottom();
        }
      }
    });

    const assistantMessage = ensureSessionMessages(sessionId)[assistantIndex];
    if (!assistantMessage?.content) {
      updateSessionMessage(sessionId, assistantIndex, {
        status: "done",
        content: "未收到 FastAGI 流式回答内容。"
      });
    } else {
      updateSessionMessage(sessionId, assistantIndex, { status: "done" });
    }
    if (datasetForRequest) {
      markSessionDatasetLoaded(sessionId, datasetForRequest);
      if (activeChatSessionId.value === sessionId) {
        attachedDataset.value = null;
      }
    }
  } catch (error) {
    const errorContent = "请求失败：" + error.message;
    if (assistantIndex >= 0 && ensureSessionMessages(sessionId)[assistantIndex]) {
      updateSessionMessage(sessionId, assistantIndex, {
        status: "done",
        content: errorContent
      });
    } else {
      appendSessionMessage(sessionId, {
        id: Date.now() + 1,
        role: "assistant",
        content: errorContent
      });
    }
  } finally {
    isSending.value = false;
    saveChatSessions();
    await scrollToBottom();
  }
}
function findAttachedDataset() {
  if (!attachedDataset.value?.id) {
    return null;
  }
  return datasets.value.find((dataset) => dataset.id === attachedDataset.value.id) || null;
}

function buildAgentQuery(userQuery, dataset) {
  if (!dataset) {
    return userQuery;
  }

  const datasetContext = buildDatasetContext(dataset);
  if (!datasetContext) {
    return userQuery;
  }

  return [
    "用户问题：",
    userQuery,
    "",
    "以下是用户本次选择的实验数据解析结果，请结合这些结果进行回答；如果证据不足，请明确说明：",
    datasetContext
  ].join("\n");
}

function buildDatasetContext(dataset) {
  const sections = [
    `实验数据名称：${getDatasetDisplayName(dataset)}`,
    `原始文件名：${dataset.fileName || dataset.name}`,
    `解析参数：TOPK=${dataset.topK}`,
    `比较结果数量：${dataset.resultCount}`
  ];

  const groupEntries = Object.entries(dataset.groupDescriptions || {});
  if (groupEntries.length) {
    sections.push(
      "实验分组：",
      groupEntries
        .slice(0, 12)
        .map(([group, description]) => `- ${group}: ${description || "无描述"}`)
        .join("\n")
    );
  }

  const resultSummaries = (dataset.results || []).slice(0, 8).map((result) => {
    const lines = [
      `### ${result.omics_type || "omics"} / ${result.comparison || "comparison"}`,
      result.llm_text ? `解析摘要：${result.llm_text}` : "",
      buildTopRowsText(result.top || [])
    ].filter(Boolean);
    return lines.join("\n");
  });

  if (resultSummaries.length) {
    sections.push("解析结果摘要：", resultSummaries.join("\n\n"));
  }

  if (dataset.warnings?.length) {
    sections.push("解析警告：", dataset.warnings.slice(0, 10).map((warning) => `- ${warning}`).join("\n"));
  }

  return limitText(sections.filter(Boolean).join("\n\n"), 16000);
}

function buildTopRowsText(rows) {
  if (!rows.length) {
    return "";
  }
  const items = rows.slice(0, 10).map((row, index) => {
    const values = [
      `feature=${row.feature}`,
      row.log2fc != null ? `log2fc=${formatNumber(row.log2fc)}` : "",
      row.fold_change != null ? `fold_change=${formatNumber(row.fold_change)}` : "",
      row.p_value != null ? `p=${formatNumber(row.p_value)}` : "",
      row.p_adjusted != null ? `p_adj=${formatNumber(row.p_adjusted)}` : ""
    ].filter(Boolean);
    return `${index + 1}. ${values.join(", ")}`;
  });
  return ["TOP features：", ...items].join("\n");
}

function formatNumber(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  if (Math.abs(numeric) < 0.001 && numeric !== 0) {
    return numeric.toExponential(3);
  }
  return numeric.toFixed(4);
}

function limitText(text, maxLength) {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}\n\n[解析结果过长，已截断到 ${maxLength} 字符]`;
}

function handleComposerKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

async function scrollToBottom() {
  await nextTick();
  scheduleChatScrollToBottom();
}

function scheduleChatScrollToBottom() {
  forceChatScrollToBottom();
  requestAnimationFrame(() => {
    forceChatScrollToBottom();
    requestAnimationFrame(forceChatScrollToBottom);
  });
  setTimeout(forceChatScrollToBottom, 80);
  setTimeout(forceChatScrollToBottom, 180);
}

function forceChatScrollToBottom() {
  const container = chatThread.value;
  if (!container) {
    return;
  }
  const bottom = Math.max(0, container.scrollHeight - container.clientHeight + CHAT_SCROLL_BOTTOM_PADDING);
  container.scrollTo({ top: bottom, behavior: "auto" });
}

async function loadDatasets() {
  try {
    const remoteDatasets = await listExperimentDatasets();
    datasets.value = remoteDatasets.map(normalizeDataset);
    datasetStorageMode.value = "postgres";
    saveDatasets();
    if (!previewDatasetId.value && datasets.value.length) {
      previewDatasetId.value = datasets.value[0].id;
    }
  } catch (error) {
    datasetStorageMode.value = "local";
    try {
      datasets.value = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]").map(normalizeDataset);
    } catch {
      datasets.value = [];
    }
    datasetStatus.value = {
      type: "idle",
      message: `数据库数据集接口暂不可用，当前使用浏览器本地缓存：${error.message}`
    };
  }
}

function saveDatasets() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(datasets.value));
}

function normalizeDataset(dataset) {
  const displayName = dataset.displayName || dataset.display_name || dataset.name || dataset.fileName || dataset.file_name || "未命名实验数据";
  return {
    id: dataset.id,
    displayName,
    name: displayName,
    fileName: dataset.fileName || dataset.file_name || dataset.name || "",
    size: dataset.size ?? dataset.file_size ?? 0,
    topK: dataset.topK ?? dataset.top_k ?? 100,
    createdAt: dataset.createdAt || dataset.created_at || new Date().toISOString(),
    updatedAt: dataset.updatedAt || dataset.updated_at || dataset.createdAt || dataset.created_at || new Date().toISOString(),
    groupDescriptions: dataset.groupDescriptions || dataset.group_descriptions || {},
    warnings: dataset.warnings || [],
    resultCount: dataset.resultCount ?? dataset.result_count ?? dataset.results?.length ?? 0,
    results: dataset.results || [],
    metadata: dataset.metadata || {}
  };
}

function getDatasetDisplayName(dataset) {
  return dataset?.displayName || dataset?.name || dataset?.fileName || "未命名实验数据";
}

function getDefaultDatasetDisplayName(file) {
  return String(file?.name || "实验数据").replace(/\.xlsx$/i, "");
}

function chooseDatasetFile() {
  datasetFileInput.value?.click();
}

function handleDatasetFile(event) {
  selectedDatasetFile.value = event.target.files?.[0] || null;
  if (selectedDatasetFile.value && !datasetDisplayName.value.trim()) {
    datasetDisplayName.value = getDefaultDatasetDisplayName(selectedDatasetFile.value);
  }
  event.target.value = "";
  datasetStatus.value = { type: "idle", message: "" };
}

async function parseSelectedDataset() {
  if (!selectedDatasetFile.value) {
    datasetStatus.value = { type: "error", message: "请先选择一个 .xlsx 文件。" };
    return;
  }
  await parseAndSaveDataset(selectedDatasetFile.value, datasetTopK.value, datasetDisplayName.value);
  selectedDatasetFile.value = null;
  datasetDisplayName.value = "";
}

async function legacyParseAndSaveDataset(file, topK, displayName = "") {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    datasetStatus.value = { type: "error", message: "仅支持上传 .xlsx 实验数据文件。" };
    return null;
  }

  isParsingDataset.value = true;
  datasetStatus.value = { type: "idle", message: "正在解析实验数据..." };
  try {
    const parsed = await analyzeOmicsFile(file, { top_n: Number(topK) || 100 });
    const item = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: file.name,
      size: file.size,
      topK: Number(topK) || 100,
      createdAt: new Date().toISOString(),
      groupDescriptions: parsed.group_descriptions || {},
      warnings: parsed.warnings || [],
      resultCount: parsed.results?.length || 0,
      results: parsed.results || []
    };
    datasets.value = [item, ...datasets.value];
    saveDatasets();
    datasetStatus.value = {
      type: "success",
      message: `解析成功，已保存 ${item.resultCount} 个比较结果。`
    };
    return item;
  } catch (error) {
    datasetStatus.value = { type: "error", message: `解析失败：${error.message}` };
    return null;
  } finally {
    isParsingDataset.value = false;
  }
}

function legacyDeleteDataset(datasetId) {
  datasets.value = datasets.value.filter((dataset) => dataset.id !== datasetId);
  if (attachedDataset.value?.id === datasetId) {
    attachedDataset.value = null;
  }
  saveDatasets();
}

async function parseAndSaveDataset(file, topK, displayName = "") {
  if (!file.name.toLowerCase().endsWith(".xlsx")) {
    datasetStatus.value = { type: "error", message: "仅支持上传 .xlsx 实验数据文件。" };
    return null;
  }

  isParsingDataset.value = true;
  datasetStatus.value = { type: "idle", message: "正在解析实验数据..." };
  try {
    const parsed = await analyzeOmicsFile(file, { top_n: Number(topK) || 100 });
    const payload = {
      display_name: displayName.trim() || getDefaultDatasetDisplayName(file),
      file_name: file.name,
      file_size: file.size,
      top_k: Number(topK) || 100,
      group_descriptions: parsed.group_descriptions || {},
      warnings: parsed.warnings || [],
      results: parsed.results || [],
      metadata: { source: "xlsx-upload" }
    };
    let item;
    if (datasetStorageMode.value === "postgres") {
      item = normalizeDataset(await createExperimentDataset(payload));
    } else {
      item = normalizeDataset({
        ...payload,
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        created_at: new Date().toISOString(),
        result_count: payload.results.length
      });
    }
    datasets.value = [item, ...datasets.value.filter((dataset) => dataset.id !== item.id)];
    previewDatasetId.value = item.id;
    saveDatasets();
    datasetStatus.value = {
      type: "success",
      message: `解析成功，已${datasetStorageMode.value === "postgres" ? "保存到数据库" : "保存到本地缓存"} ${item.resultCount} 个比较结果。`
    };
    return item;
  } catch (error) {
    datasetStatus.value = { type: "error", message: `解析失败：${error.message}` };
    return null;
  } finally {
    isParsingDataset.value = false;
  }
}

function startRenameDataset(dataset) {
  editingDatasetId.value = dataset.id;
  editingDatasetName.value = getDatasetDisplayName(dataset);
}

function cancelRenameDataset() {
  editingDatasetId.value = null;
  editingDatasetName.value = "";
}

async function renameDataset(datasetId) {
  const name = editingDatasetName.value.trim();
  if (!name) {
    datasetStatus.value = { type: "error", message: "实验数据名称不能为空。" };
    return;
  }
  const current = datasets.value.find((dataset) => dataset.id === datasetId);
  if (!current) {
    return;
  }
  try {
    let updated;
    if (datasetStorageMode.value === "postgres") {
      updated = normalizeDataset(await updateExperimentDataset(datasetId, { display_name: name }));
    } else {
      updated = { ...current, displayName: name, name, updatedAt: new Date().toISOString() };
    }
    datasets.value = datasets.value.map((dataset) => (dataset.id === datasetId ? updated : dataset));
    if (attachedDataset.value?.id === datasetId) {
      attachedDataset.value = { ...attachedDataset.value, name: getDatasetDisplayName(updated) };
    }
    editingDatasetId.value = null;
    editingDatasetName.value = "";
    saveDatasets();
    datasetStatus.value = { type: "success", message: "实验数据名称已更新。" };
  } catch (error) {
    datasetStatus.value = { type: "error", message: `更新失败：${error.message}` };
  }
}

function previewDatasetDetails(dataset) {
  previewDatasetId.value = dataset.id;
  const firstGroup = getDatasetPreviewGroups(dataset).find((group) => group.rows.length) || getDatasetPreviewGroups(dataset)[0];
  activeDatasetPreviewGroupId.value = firstGroup?.id || "";
  datasetPreviewOpen.value = true;
}

function closeDatasetPreview() {
  datasetPreviewOpen.value = false;
}

function selectDatasetPreviewGroup(groupId) {
  activeDatasetPreviewGroupId.value = groupId;
}

function getDatasetPreviewRows(dataset) {
  return (dataset?.results || [])
    .flatMap((result) =>
      sortDatasetPreviewRows(result.top || []).map((row) => ({
        omicsType: result.omics_type || "omics",
        comparison: result.comparison || "comparison",
        ...row
      }))
    );
}

function getDatasetPreviewGroups(dataset) {
  return (dataset?.results || []).map((result) => ({
    id: getDatasetResultLabel(result),
    label: getDatasetResultLabel(result),
    omicsType: result.omics_type || "omics",
    comparison: result.comparison || "comparison",
    rows: sortDatasetPreviewRows(result.top || [])
  }));
}

function sortDatasetPreviewRows(rows) {
  return [...rows].sort((left, right) => getDatasetRowPValue(left) - getDatasetRowPValue(right));
}

function getDatasetRowPValue(row) {
  const adjusted = Number(row?.p_adjusted);
  if (Number.isFinite(adjusted)) {
    return adjusted;
  }
  const raw = Number(row?.p_value);
  return Number.isFinite(raw) ? raw : Number.POSITIVE_INFINITY;
}

function getDatasetResultLabel(result) {
  return `${result.omics_type || "omics"} / ${result.comparison || "comparison"}`;
}

async function deleteDataset(datasetId) {
  try {
    if (datasetStorageMode.value === "postgres") {
      await deleteExperimentDataset(datasetId);
    }
    datasets.value = datasets.value.filter((dataset) => dataset.id !== datasetId);
    if (previewDatasetId.value === datasetId) {
      previewDatasetId.value = datasets.value[0]?.id || null;
      datasetPreviewOpen.value = false;
    }
    if (attachedDataset.value?.id === datasetId) {
      attachedDataset.value = null;
    }
    saveDatasets();
    datasetStatus.value = { type: "success", message: "实验数据已删除。" };
  } catch (error) {
    datasetStatus.value = { type: "error", message: `删除失败：${error.message}` };
  }
}

async function runGraphSearch() {
  const queries = splitGraphQueries(graphQuery.value);
  if (!queries.length) {
    graphStatus.value = "请输入搜索词";
    return;
  }

  const previousNodeIds = new Set(graphNodes.value.map((node) => node.id));
  graphStatus.value = "searching";
  hoveredGraphItem.value = null;
  selectedGraphItem.value = null;
  const warnings = [];
  try {
    for (const query of queries) {
      const response = await searchGraphNodes({
        name: query,
        depth: getGraphSearchDepth(),
        direction: "both",
        limit: graphLimit,
        include_properties: true,
        llm_text: false,
        vector_search: graphVectorSearch.value || graphRerank.value,
        top_k: 20,
        rerank: graphRerank.value,
        vector_top_k: 20,
        rerank_top_n: 2
      });
      addGraphSearchResult(query, response);
      warnings.push(...(response.warnings || []));
      const proteinInteractionResponse = await fetchProteinInteractionGraph(query);
      if (proteinInteractionResponse) {
        addGraphSearchResult(query, proteinInteractionResponse);
        warnings.push(...(proteinInteractionResponse.warnings || []));
      }
    }
    recomputeGraphData(warnings);
    stageGraphReveal(previousNodeIds);
    await nextTick();
    rebuildGraphScene(previousNodeIds, graphAnchors.value.length > 1 ? "DualCoreTransition" : "SingleCoreLayout");
    graphQuery.value = "";
    graphStatus.value = "done";
  } catch (error) {
    graphData.value = { ...graphData.value, warnings: [error.message] };
    graphStatus.value = "error";
  }
}

async function fetchProteinInteractionGraph(query) {
  try {
    const response = await getGraphRelationships({
      name: query,
      relationship_type: "PROTEIN_INTERACTS_WITH",
      labels: ["Protein"],
      target_labels: ["Protein"],
      direction: "both",
      limit: graphLimit,
      include_properties: true
    });
    if (!response.nodes?.length && !response.relationships?.length) {
      return null;
    }
    return response;
  } catch (error) {
    return {
      query,
      matched_nodes: [],
      nodes: [],
      relationships: [],
      warnings: [`蛋白互作网络加载失败：${error.message}`]
    };
  }
}

function splitGraphQueries(value) {
  return String(value || "")
    .split(/[;；]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getGraphSearchDepth() {
  return Math.max(1, Math.min(5, Number(graphDepth.value) || 1));
}

function addGraphSearchResult(query, response) {
  const nodes = response.nodes || response.matched_nodes || [];
  const relationships = response.relationships || [];
  const matchedNodes = response.matched_nodes?.length ? response.matched_nodes : findGraphSearchAnchorNodes(nodes, query);
  const anchors = matchedNodes.length ? selectGraphCoreCandidates(matchedNodes) : nodes.slice(0, 1);
  anchors.forEach((node) => {
    if (!node?.id) {
      return;
    }
    const anchorId = node.id;
    if (!graphAnchors.value.some((anchor) => anchor.id === anchorId)) {
      graphAnchors.value.push({
        id: anchorId,
        query,
        name: node.name || query,
        node,
        createdAt: Date.now()
      });
    }
    graphAnchorResults.value[anchorId] = {
      nodes,
      relationships,
      warnings: response.warnings || []
    };
  });
}

function findGraphSearchAnchorNodes(nodes, query) {
  const exactMatches = nodes.filter((node) => sameGraphName(node.name, query));
  const typedMatches = exactMatches.filter((node) => ["Gene", "Protein"].includes(getNodeType(node)));
  if (typedMatches.length >= 2) {
    return typedMatches;
  }
  const queryKey = normalizeGraphName(query);
  const compatibleMatches = nodes.filter((node) => {
    const nodeKey = normalizeGraphName(node.name);
    return nodeKey === queryKey || nodeKey === `${queryKey}gene` || nodeKey === `${queryKey}protein`;
  });
  const compatibleTypedMatches = compatibleMatches.filter((node) => ["Gene", "Protein"].includes(getNodeType(node)));
  return compatibleTypedMatches.length ? compatibleTypedMatches : exactMatches;
}

function sameGraphName(value, query) {
  return normalizeGraphName(value) === normalizeGraphName(query);
}

function normalizeGraphName(value) {
  return String(value || "").trim().toLowerCase().replace(/[\s_-]+/g, "");
}

function recomputeGraphData(extraWarnings = []) {
  const nodeMap = new Map();
  const relationshipMap = new Map();
  const warnings = [...extraWarnings];
  graphAnchors.value.forEach((anchor) => {
    const result = graphAnchorResults.value[anchor.id];
    if (!result) {
      return;
    }
    (result.nodes || []).forEach((node) => nodeMap.set(node.id, node));
    (result.relationships || []).forEach((relationship) => relationshipMap.set(relationship.id, relationship));
    warnings.push(...(result.warnings || []));
  });
  Object.values(graphExpansionResults.value).forEach((result) => {
    (result.nodes || []).forEach((node) => nodeMap.set(node.id, node));
    (result.relationships || []).forEach((relationship) => relationshipMap.set(relationship.id, relationship));
    warnings.push(...(result.warnings || []));
  });
  graphData.value = {
    nodes: Array.from(nodeMap.values()),
    relationships: Array.from(relationshipMap.values()),
    warnings: [...new Set(warnings)]
  };
}

function snapshotGraphPositions() {
  const positions = { ...graphNodePositions.value };
  graphScene.value.nodes.forEach((node) => {
    positions[node.id] = { x: node.x, y: node.y };
  });
  graphNodePositions.value = positions;
}

function clearGraphRevealTimers() {
  while (graphRevealTimers.length) {
    clearTimeout(graphRevealTimers.pop());
  }
}

function stageGraphReveal(previousNodeIds = new Set()) {
  clearGraphRevealTimers();
  const allIds = graphNodes.value.map((node) => node.id);
  if (!allIds.length) {
    graphVisibleNodeIds.value = new Set();
    graphEnteringNodeIds.value = new Set();
    return;
  }

  const allIdSet = new Set(allIds);
  const anchorIds = new Set(graphAnchors.value.map((anchor) => anchor.id).filter((id) => allIdSet.has(id)));
  const immediateIds = new Set([...previousNodeIds, ...anchorIds].filter((id) => allIdSet.has(id)));
  graphVisibleNodeIds.value = immediateIds.size ? immediateIds : new Set(allIds.slice(0, 1));

  const delayedIds = allIds.filter((id) => !graphVisibleNodeIds.value.has(id));
  delayedIds.forEach((id, index) => {
    const delay = 80 + index * 38;
    const timer = setTimeout(() => {
      graphVisibleNodeIds.value = new Set([...graphVisibleNodeIds.value, id]);
      graphEnteringNodeIds.value = new Set([...graphEnteringNodeIds.value, id]);
      const exitTimer = setTimeout(() => {
        graphEnteringNodeIds.value = new Set([...graphEnteringNodeIds.value].filter((item) => item !== id));
      }, 320);
      graphRevealTimers.push(exitTimer);
    }, delay);
    graphRevealTimers.push(timer);
  });
}

function focusGraphAnchor(anchor) {
  const node = graphNodes.value.find((item) => item.id === anchor.id) || anchor.node;
  selectedGraphItem.value = { kind: "node", item: node };
  hoveredGraphItem.value = selectedGraphItem.value;
  const sceneNode = graphScene.value.nodes.find((item) => item.id === anchor.id);
  if (sceneNode) {
    centerGraphOn(sceneNode.x, sceneNode.y);
  }
}

function hoverGraphAnchor(anchor) {
  const node = graphNodes.value.find((item) => item.id === anchor.id) || anchor.node;
  hoveredGraphItem.value = { kind: "node", item: node };
}

function removeGraphAnchor(anchorId) {
  const previousNodeIds = new Set(graphNodes.value.map((node) => node.id));
  graphAnchors.value = graphAnchors.value.filter((anchor) => anchor.id !== anchorId);
  delete graphAnchorResults.value[anchorId];
  if (selectedGraphItem.value?.item?.id === anchorId) {
    selectedGraphItem.value = null;
  }
  if (hoveredGraphItem.value?.item?.id === anchorId) {
    hoveredGraphItem.value = null;
  }
  graphNodePositions.value = {};
  recomputeGraphData();
  stageGraphReveal(previousNodeIds);
  nextTick(() => rebuildGraphScene(previousNodeIds, graphAnchors.value.length > 1 ? "DualCoreTransition" : "SingleCoreLayout"));
}

function clearGraphAnchors() {
  clearGraphRevealTimers();
  graphAnchors.value = [];
  graphAnchorResults.value = {};
  graphExpansionResults.value = {};
  graphData.value = { nodes: [], relationships: [], warnings: [] };
  graphVisibleNodeIds.value = new Set();
  graphEnteringNodeIds.value = new Set();
  graphNodePositions.value = {};
  graphScene.value = { width: 1600, height: 900, nodes: [], relationships: [], state: "Idle" };
  graphViewport.value = { x: 0, y: 0, scale: 1 };
  hoveredGraphItem.value = null;
  selectedGraphItem.value = null;
  graphTooltip.value = null;
  graphStatus.value = "ready";
  drawGraphScene();
  drawGraphMinimap();
}

function rebuildGraphScene(previousNodeIds = new Set(), state = "SingleCoreLayout") {
  graphScene.value.nodes.forEach((node) => {
    graphNodePositions.value[node.id] = { x: node.x, y: node.y };
  });
  graphScene.value = buildGraphCanvasScene(graphNodes.value, graphRelationships.value, previousNodeIds, state);
  graphScene.value.nodes.forEach((node) => {
    graphNodePositions.value[node.id] = { x: node.targetX, y: node.targetY };
  });
  graphAnimationStartedAt = performance.now();
  cancelAnimationFrame(graphAnimationFrame);
  graphAnimationFrame = requestAnimationFrame(animateGraphScene);
  fitGraphToView();
}

function buildGraphCanvasScene(nodes, relationships, previousNodeIds, state) {
  const stage = graphCanvasStageRef.value;
  const width = Math.max(1600, stage?.clientWidth || 1100);
  const height = Math.max(900, stage?.clientHeight || 620);
  const centerX = width / 2;
  const centerY = height / 2;
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const cores = selectGraphCoreCandidates(graphAnchors.value.map((anchor) => nodeById.get(anchor.id)).filter(Boolean));
  const coreIds = new Set(cores.map((node) => node.id));
  const adjacency = buildGraphAdjacency(relationships);
  const distancesByCore = new Map(cores.map((core) => [core.id, getHopDistances(core.id, relationships)]));
  const degreeByNode = countGraphDegrees(nodes, relationships);
  const pathRelationshipIds = findBridgeRelationshipIds(cores.map((node) => ({ id: node.id })), relationships);
  const pathNodeIds = findPathNodeIds(pathRelationshipIds, relationships);
  const roles = classifyCanvasNodeRoles(nodes, cores, distancesByCore, pathNodeIds);
  const corePositions = getCanvasCorePositions(cores.length, centerX, centerY, roles);
  const semanticLayout = createCanvasSemanticLayout(nodes, cores, corePositions, distancesByCore, adjacency, roles);
  const modelNodes = nodes.map((node) => {
    const role = roles.get(node.id) || "context";
    const depth = getNodeDepth(node.id, distancesByCore);
    const target = computeCanvasNodeTarget(node, role, depth, cores, corePositions, distancesByCore, adjacency, nodes, semanticLayout);
    const visual = getCanvasNodeVisual(node, role, depth, degreeByNode.get(node.id) || 0);
    const previous = graphScene.value.nodes.find((item) => item.id === node.id) || null;
    const saved = graphNodePositions.value[node.id];
    const parent = findNearestCorePosition(node.id, cores, corePositions, distancesByCore) || { x: centerX, y: centerY };
    const isPrimaryCore = coreIds.has(node.id);
    const isSecondaryCore = isCanvasSecondaryCoreRole(role);
    const isExisting = previousNodeIds.has(node.id) || Boolean(previous || saved);
    return {
      ...node,
      role,
      depth,
      ownerCoreIndex: semanticLayout.ownerCoreIndexByNode.get(node.id) ?? -1,
      secondaryParentId: semanticLayout.secondaryParentByNode.get(node.id) || null,
      degree: degreeByNode.get(node.id) || 0,
      targetX: target.x,
      targetY: target.y,
      x: previous?.x ?? saved?.x ?? (isExisting ? target.x : parent.x),
      y: previous?.y ?? saved?.y ?? (isExisting ? target.y : parent.y),
      opacity: previous?.opacity ?? (isExisting ? visual.opacity : 0),
      scale: previous?.scale ?? (isExisting ? 1 : 0.4),
      radius: visual.radius,
      color: visual.color,
      borderColor: visual.borderColor,
      labelVisible: visual.labelVisible,
      glow: visual.glow,
      fixed: isPrimaryCore,
      locked: isPrimaryCore || isSecondaryCore
    };
  });
  relaxCanvasNodes(modelNodes, relationships);
  const modelById = new Map(modelNodes.map((node) => [node.id, node]));
  const modelRelationships = relationships
    .map((relationship) => ({
      ...relationship,
      source: modelById.get(relationship.source_id),
      target: modelById.get(relationship.target_id),
      inPath: pathRelationshipIds.has(relationship.id),
      progress: previousNodeIds.has(relationship.source_id) && previousNodeIds.has(relationship.target_id) ? 1 : 0,
      curve: getParallelEdgeCurve(relationship, relationships),
      visual: getCanvasEdgeVisual(relationship, pathRelationshipIds.has(relationship.id), modelById.get(relationship.source_id), modelById.get(relationship.target_id))
    }))
    .filter((relationship) => relationship.source && relationship.target);

  return {
    width,
    height,
    nodes: modelNodes,
    relationships: modelRelationships,
    state,
    pathRelationshipIds,
    pathNodeIds
  };
}

function buildGraphAdjacency(relationships) {
  const adjacency = new Map();
  relationships.forEach((relationship) => {
    if (!adjacency.has(relationship.source_id)) {
      adjacency.set(relationship.source_id, []);
    }
    if (!adjacency.has(relationship.target_id)) {
      adjacency.set(relationship.target_id, []);
    }
    adjacency.get(relationship.source_id).push(relationship.target_id);
    adjacency.get(relationship.target_id).push(relationship.source_id);
  });
  return adjacency;
}

function getHopDistances(targetId, relationships) {
  const adjacency = buildGraphAdjacency(relationships);
  const distances = new Map([[targetId, 0]]);
  const queue = [targetId];
  while (queue.length) {
    const current = queue.shift();
    const nextDistance = distances.get(current) + 1;
    (adjacency.get(current) || []).forEach((neighborId) => {
      if (!distances.has(neighborId)) {
        distances.set(neighborId, nextDistance);
        queue.push(neighborId);
      }
    });
  }
  return distances;
}

function countGraphDegrees(nodes, relationships) {
  const degree = new Map(nodes.map((node) => [node.id, 0]));
  relationships.forEach((relationship) => {
    degree.set(relationship.source_id, (degree.get(relationship.source_id) || 0) + 1);
    degree.set(relationship.target_id, (degree.get(relationship.target_id) || 0) + 1);
  });
  return degree;
}

function classifyCanvasNodeRoles(nodes, cores, distancesByCore, pathNodeIds) {
  const roles = new Map();
  cores.forEach((core, index) => roles.set(core.id, index === 0 ? "coreA" : "coreB"));
  nodes.forEach((node) => {
    if (roles.has(node.id)) {
      return;
    }
    const connected = cores.filter((core) => (distancesByCore.get(core.id)?.get(node.id) || Infinity) <= 1);
    const oneHopCore = cores.find((core) => distancesByCore.get(core.id)?.get(node.id) === 1);
    if (pathNodeIds.has(node.id) || connected.length > 1) {
      roles.set(node.id, "bridge");
    } else if (oneHopCore?.id === cores[0]?.id) {
      roles.set(node.id, "secondaryCoreA");
    } else if (oneHopCore?.id === cores[1]?.id) {
      roles.set(node.id, "secondaryCoreB");
    } else if (getNearestCoreIndex(node.id, cores, distancesByCore) === 0) {
      roles.set(node.id, "clusterA");
    } else if (getNearestCoreIndex(node.id, cores, distancesByCore) === 1) {
      roles.set(node.id, "clusterB");
    } else {
      roles.set(node.id, "context");
    }
  });
  return roles;
}

function isCanvasPrimaryCoreRole(role) {
  return role === "coreA" || role === "coreB";
}

function isCanvasSecondaryCoreRole(role) {
  return role === "secondaryCoreA" || role === "secondaryCoreB";
}

function getNearestCoreIndex(nodeId, cores, distancesByCore) {
  let nearest = { index: -1, distance: Infinity };
  cores.forEach((core, index) => {
    const distance = distancesByCore.get(core.id)?.get(nodeId) ?? Infinity;
    if (distance < nearest.distance) {
      nearest = { index, distance };
    }
  });
  return nearest.index;
}

function createCanvasSemanticLayout(nodes, cores, corePositions, distancesByCore, adjacency, roles) {
  const ownerCoreIndexByNode = new Map();
  const secondaryCoreIdsByCore = new Map(cores.map((_, index) => [index, []]));
  nodes.forEach((node) => {
    const ownerIndex = getNearestCoreIndex(node.id, cores, distancesByCore);
    ownerCoreIndexByNode.set(node.id, ownerIndex);
    if (isCanvasSecondaryCoreRole(roles.get(node.id))) {
      secondaryCoreIdsByCore.get(ownerIndex)?.push(node.id);
    }
  });

  const secondaryTargetByNode = new Map();
  secondaryCoreIdsByCore.forEach((secondaryIds, coreIndex) => {
    const corePosition = corePositions[coreIndex] || corePositions[0] || { x: 800, y: 450 };
    secondaryIds.forEach((nodeId, index) => {
      secondaryTargetByNode.set(nodeId, computeSecondaryCoreTarget(nodeId, index, secondaryIds.length, corePosition, cores.length, coreIndex));
    });
  });

  const secondaryParentByNode = new Map();
  nodes.forEach((node) => {
    const role = roles.get(node.id);
    if (isCanvasPrimaryCoreRole(role) || isCanvasSecondaryCoreRole(role) || role === "bridge") {
      return;
    }
    const ownerIndex = ownerCoreIndexByNode.get(node.id);
    const parentId = findSecondaryParentId(node.id, ownerIndex, adjacency, roles, ownerCoreIndexByNode, distancesByCore, cores);
    if (parentId) {
      secondaryParentByNode.set(node.id, parentId);
    }
  });

  return {
    ownerCoreIndexByNode,
    secondaryCoreIdsByCore,
    secondaryTargetByNode,
    secondaryParentByNode
  };
}

function computeSecondaryCoreTarget(nodeId, index, total, corePosition, coreCount, coreIndex) {
  const slotsPerRing = 12;
  const ring = Math.floor(index / slotsPerRing);
  const slot = index % slotsPerRing;
  const radius = getGraphHopDistance(1 + ring);
  const ringOffset = ring * (Math.PI / 12);
  const angle = -Math.PI / 2 + (Math.PI * 2 * slot) / slotsPerRing + ringOffset;
  return {
    x: corePosition.x + Math.cos(angle) * radius,
    y: corePosition.y + Math.sin(angle) * radius
  };
}

function findSecondaryParentId(nodeId, ownerIndex, adjacency, roles, ownerCoreIndexByNode, distancesByCore, cores) {
  const candidates = (adjacency.get(nodeId) || []).filter((neighborId) => {
    const role = roles.get(neighborId);
    return isCanvasSecondaryCoreRole(role) && ownerCoreIndexByNode.get(neighborId) === ownerIndex;
  });
  if (candidates.length) {
    return candidates.sort((a, b) => String(a).localeCompare(String(b)))[0];
  }

  const ownerCore = cores[ownerIndex];
  if (!ownerCore) {
    return null;
  }
  const ownerDistances = distancesByCore.get(ownerCore.id);
  let best = null;
  (adjacency.get(nodeId) || []).forEach((neighborId) => {
    const neighborDepth = ownerDistances?.get(neighborId);
    if (!Number.isFinite(neighborDepth)) {
      return;
    }
    if (!best || neighborDepth < best.depth) {
      best = { id: neighborId, depth: neighborDepth };
    }
  });
  return best?.depth === 1 ? best.id : null;
}

function getGraphHopDistance(depth) {
  const normalizedDepth = Math.max(1, Number(depth) || 1);
  return GRAPH_CORE_DISTANCE * (GRAPH_CORE_FIRST_HOP_RATIO + (normalizedDepth - 1) * GRAPH_CORE_HOP_RATIO_STEP);
}

function sortGraphCoreCandidates(nodes) {
  return [...nodes].sort((left, right) => {
    const leftTypeRank = getGraphCoreTypeRank(left);
    const rightTypeRank = getGraphCoreTypeRank(right);
    if (leftTypeRank !== rightTypeRank) {
      return leftTypeRank - rightTypeRank;
    }
    const leftName = normalizeGraphName(left?.name);
    const rightName = normalizeGraphName(right?.name);
    if (leftName !== rightName) {
      return leftName.localeCompare(rightName);
    }
    return String(left?.id || "").localeCompare(String(right?.id || ""));
  });
}

function selectGraphCoreCandidates(nodes) {
  const sortedNodes = sortGraphCoreCandidates(nodes);
  const geneProteinPair = findGeneProteinCorePair(sortedNodes);
  if (geneProteinPair.length) {
    return geneProteinPair;
  }
  return sortedNodes.slice(0, 2);
}

function findGeneProteinCorePair(nodes) {
  const geneByName = new Map();
  const proteinByName = new Map();
  nodes.forEach((node) => {
    const baseName = getGraphEntityBaseName(node);
    if (!baseName) {
      return;
    }
    const type = getNodeType(node);
    if (type === "Gene" && !geneByName.has(baseName)) {
      geneByName.set(baseName, node);
    }
    if (type === "Protein" && !proteinByName.has(baseName)) {
      proteinByName.set(baseName, node);
    }
  });
  const pairedName = [...geneByName.keys()].find((name) => proteinByName.has(name));
  return pairedName ? [geneByName.get(pairedName), proteinByName.get(pairedName)] : [];
}

function getGraphEntityBaseName(node) {
  return normalizeGraphName(node?.name).replace(/(gene|protein)$/i, "");
}

function getGraphCoreTypeRank(node) {
  const type = getNodeType(node);
  if (type === "Gene") {
    return 0;
  }
  if (type === "Protein") {
    return 1;
  }
  return 2;
}

function getCanvasCorePositions(coreCount, centerX, centerY, roles = new Map()) {
  if (coreCount <= 1) {
    return [{ x: centerX, y: centerY }];
  }
  const halfDistance = getCanvasCoreDistance(roles) / 2;
  return [
    { x: centerX - halfDistance, y: centerY },
    { x: centerX + halfDistance, y: centerY }
  ];
}

function getCanvasCoreDistance(roles) {
  const extraRings = Math.max(
    getCanvasCoreExtraRings(roles, "secondaryCoreA"),
    getCanvasCoreExtraRings(roles, "secondaryCoreB")
  );
  return GRAPH_CORE_DISTANCE * (1 + extraRings * GRAPH_CORE_HOP_RATIO_STEP);
}

function getCanvasCoreExtraRings(roles, secondaryRole) {
  const nodeCount = [...roles.values()].filter((role) => role === secondaryRole).length;
  return Math.max(0, Math.ceil(nodeCount / 12) - 1);
}

function computeCanvasNodeTarget(node, role, depth, cores, corePositions, distancesByCore, adjacency, nodes, semanticLayout) {
  const nodeIndex = Math.max(0, nodes.findIndex((item) => item.id === node.id));
  if (role === "coreA") {
    return corePositions[0];
  }
  if (role === "coreB") {
    return corePositions[1] || corePositions[0];
  }
  if (isCanvasSecondaryCoreRole(role)) {
    return semanticLayout.secondaryTargetByNode.get(node.id) || findNearestCorePosition(node.id, cores, corePositions, distancesByCore) || corePositions[0];
  }
  if (role === "bridge" && corePositions.length > 1) {
    const bridgeNodes = nodes.filter((item) => {
      if (item.id === node.id) return true;
      const linkedToBoth = cores.every((core) => (distancesByCore.get(core.id)?.get(item.id) || Infinity) <= 1);
      return linkedToBoth;
    });
    const index = Math.max(0, bridgeNodes.findIndex((item) => item.id === node.id));
    const offset = (index - (bridgeNodes.length - 1) / 2) * 58;
    return {
      x: (corePositions[0].x + corePositions[1].x) / 2,
      y: (corePositions[0].y + corePositions[1].y) / 2 + offset
    };
  }
  const secondaryParentId = semanticLayout.secondaryParentByNode.get(node.id);
  const secondaryParentTarget = secondaryParentId ? semanticLayout.secondaryTargetByNode.get(secondaryParentId) : null;
  if (secondaryParentTarget && depth >= 2) {
    const ownerIndex = semanticLayout.ownerCoreIndexByNode.get(node.id);
    const owner = corePositions[ownerIndex] || corePositions[0] || { x: 800, y: 450 };
    const siblings = nodes.filter((item) => semanticLayout.secondaryParentByNode.get(item.id) === secondaryParentId && getNodeDepth(item.id, distancesByCore) === depth);
    const index = Math.max(0, siblings.findIndex((item) => item.id === node.id));
    const slotCount = Math.min(8, Math.max(1, siblings.length));
    const slot = index % slotCount;
    const ring = Math.floor(index / slotCount);
    const outwardAngle = Math.atan2(secondaryParentTarget.y - owner.y, secondaryParentTarget.x - owner.x);
    const spread = Math.PI * 0.92;
    const angle = outwardAngle - spread / 2 + (slotCount <= 1 ? 0 : (spread * slot) / Math.max(1, slotCount - 1)) + ring * 0.18;
    const radius = 170 + Math.max(0, depth - 2) * 130 + ring * 120;
    const offset = Math.sin(getStableNodeAngle(node.id)) * 20;
    return {
      x: secondaryParentTarget.x + Math.cos(angle) * (radius + offset),
      y: secondaryParentTarget.y + Math.sin(angle) * radius
    };
  }
  const owner = findNearestCorePosition(node.id, cores, corePositions, distancesByCore) || corePositions[0] || { x: 800, y: 450 };
  const side = role === "clusterA" ? -1 : role === "clusterB" ? 1 : Math.sign(nodeIndex % 2 ? 1 : -1);
  const baseRadius = getGraphHopDistance(depth);
  const spread = role === "clusterA" ? Math.PI * 0.95 : role === "clusterB" ? Math.PI * 0.95 : Math.PI * 1.7;
  const start = role === "clusterA" ? Math.PI * 0.55 : role === "clusterB" ? -Math.PI * 0.45 : -Math.PI * 0.85;
  const siblings = nodes.filter((item) => {
    const itemDepth = getNodeDepth(item.id, distancesByCore);
    const itemOwner = findNearestCorePosition(item.id, cores, corePositions, distancesByCore);
    return itemDepth === depth && itemOwner === owner;
  });
  const index = Math.max(0, siblings.findIndex((item) => item.id === node.id));
  const angle = start + (siblings.length <= 1 ? 0 : (spread * index) / (siblings.length - 1));
  const secondHopOffset = depth > 1 ? 40 * Math.sin(getStableNodeAngle(node.id)) : 0;
  return {
    x: owner.x + Math.cos(angle) * (baseRadius + secondHopOffset) * (role === "context" ? 1.18 : 1),
    y: owner.y + Math.sin(angle) * baseRadius + side * 12
  };
}

function getNodeDepth(nodeId, distancesByCore) {
  const distances = [...distancesByCore.values()].map((distanceMap) => distanceMap.get(nodeId)).filter((value) => Number.isFinite(value));
  return Math.min(...distances, 3);
}

function findNearestCorePosition(nodeId, cores, corePositions, distancesByCore) {
  let nearest = null;
  cores.forEach((core, index) => {
    const distance = distancesByCore.get(core.id)?.get(nodeId) ?? Infinity;
    if (!nearest || distance < nearest.distance) {
      nearest = { distance, position: corePositions[index] };
    }
  });
  return nearest?.position || null;
}

function getCanvasNodeVisual(node, role, depth, degree) {
  const color = getNodeColor(node);
  if (role === "coreA" || role === "coreB") {
    return { radius: 28, color, borderColor: "#0f172a", opacity: 1, labelVisible: true, glow: true };
  }
  if (isCanvasSecondaryCoreRole(role)) {
    return { radius: Math.min(24, 19 + degree * 0.55), color, borderColor: color, opacity: 0.96, labelVisible: true, glow: false };
  }
  if (role === "bridge") {
    return { radius: 21, color: "#F59E0B", borderColor: "#b45309", opacity: 0.94, labelVisible: true, glow: false };
  }
  if (depth <= 1) {
    return { radius: Math.min(22, 16 + degree * 0.8), color, borderColor: color, opacity: 0.9, labelVisible: graphViewport.value.scale >= 0.58, glow: false };
  }
  return { radius: 12, color, borderColor: color, opacity: 0.48, labelVisible: false, glow: false };
}

function getCanvasEdgeVisual(relationship, inPath, sourceNode = null, targetNode = null) {
  if (inPath) {
    return { width: 4, color: "#F59E0B", opacity: 0.95, arrow: true, animated: true, dash: [10, 8] };
  }
  const color = getRelationshipColor(relationship);
  const type = String(relationship?.type || "").toUpperCase();
  const isCoreEdge = graphAnchorIds.value.has(relationship.source_id) || graphAnchorIds.value.has(relationship.target_id);
  const isSecondaryCoreEdge = isCanvasSecondaryCoreRole(sourceNode?.role) || isCanvasSecondaryCoreRole(targetNode?.role);
  return {
    width: isCoreEdge ? 2.2 : isSecondaryCoreEdge ? 1.9 : type.includes("HAS") ? 1.4 : 1.7,
    color,
    opacity: isCoreEdge ? 0.64 : isSecondaryCoreEdge ? 0.48 : 0.34,
    arrow: true,
    animated: false
  };
}

function getParallelEdgeCurve(relationship, relationships) {
  const pairKey = [relationship.source_id, relationship.target_id].sort().join("|");
  const siblings = relationships.filter((item) => [item.source_id, item.target_id].sort().join("|") === pairKey);
  if (siblings.length <= 1) {
    return 0;
  }
  const index = siblings.findIndex((item) => item.id === relationship.id);
  return (index - (siblings.length - 1) / 2) * 26;
}

function relaxCanvasNodes(nodes, relationships) {
  for (let iteration = 0; iteration < 28; iteration += 1) {
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const minDistance = a.radius + b.radius + 28;
        let dx = b.targetX - a.targetX;
        let dy = b.targetY - a.targetY;
        let distance = Math.hypot(dx, dy);
        if (distance >= minDistance) {
          continue;
        }
        if (distance < 1) {
          const angle = getStableNodeAngle(`${a.id}-${b.id}`);
          dx = Math.cos(angle);
          dy = Math.sin(angle);
          distance = 1;
        }
        const push = (minDistance - distance) / 2;
        if (!a.locked) {
          a.targetX -= (dx / distance) * push;
          a.targetY -= (dy / distance) * push;
        }
        if (!b.locked) {
          b.targetX += (dx / distance) * push;
          b.targetY += (dy / distance) * push;
        }
      }
    }
  }
}

function findPathNodeIds(pathRelationshipIds, relationships) {
  const nodeIds = new Set();
  relationships.forEach((relationship) => {
    if (pathRelationshipIds.has(relationship.id)) {
      nodeIds.add(relationship.source_id);
      nodeIds.add(relationship.target_id);
    }
  });
  return nodeIds;
}

function getStableNodeAngle(value) {
  const text = String(value || "");
  let hash = 0;
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) % 6283;
  }
  return hash / 1000;
}

function getNodeType(node) {
  const labels = node?.labels || [];
  const candidates = [node?.properties?.entity_type, ...labels, node?.properties?.type].filter(Boolean);
  const normalized = candidates.find((value) => entityColors[normalizeEntityType(value)]);
  return normalizeEntityType(normalized || labels.find((label) => label !== "KGNode") || "Entity");
}

function normalizeEntityType(value) {
  const text = String(value || "").trim();
  const matched = Object.keys(entityColors).find((key) => key.toLowerCase() === text.toLowerCase());
  return matched || text || "Entity";
}

function getNodeColor(node) {
  return entityColors[getNodeType(node)] || "#94A3B8";
}

function getNodeIcon(node) {
  const iconMap = {
    Gene: Dna,
    Protein: Atom,
    Metabolite: Beaker,
    Lipid: CircleDot,
    Pathway: Network,
    Disease: Shield,
    Drug: Pill,
    Phenotype: CircleDot,
    Experiment: FlaskConical,
    Publication: FileText
  };
  return iconMap[getNodeType(node)] || Database;
}

function findSharedNodeIds(anchors, nodes, relationships) {
  if (anchors.length < 2 || !relationships.length) {
    return new Set();
  }
  const anchorIds = new Set(anchors.map((anchor) => anchor.id));
  const nodeIds = new Set(nodes.map((node) => node.id).filter((id) => !anchorIds.has(id)));
  const linkedAnchorsByNode = new Map();
  relationships.forEach((relationship) => {
    if (anchorIds.has(relationship.source_id) && nodeIds.has(relationship.target_id)) {
      const current = linkedAnchorsByNode.get(relationship.target_id) || new Set();
      current.add(relationship.source_id);
      linkedAnchorsByNode.set(relationship.target_id, current);
    }
    if (anchorIds.has(relationship.target_id) && nodeIds.has(relationship.source_id)) {
      const current = linkedAnchorsByNode.get(relationship.source_id) || new Set();
      current.add(relationship.target_id);
      linkedAnchorsByNode.set(relationship.source_id, current);
    }
  });
  return new Set([...linkedAnchorsByNode.entries()].filter(([, ids]) => ids.size > 1).map(([nodeId]) => nodeId));
}

function findBridgeRelationshipIds(anchors, relationships) {
  if (anchors.length < 2 || !relationships.length) {
    return new Set();
  }
  const anchorIds = anchors.map((anchor) => anchor.id);
  const adjacency = new Map();
  relationships.forEach((relationship) => {
    if (!adjacency.has(relationship.source_id)) {
      adjacency.set(relationship.source_id, []);
    }
    if (!adjacency.has(relationship.target_id)) {
      adjacency.set(relationship.target_id, []);
    }
    adjacency.get(relationship.source_id).push({ next: relationship.target_id, relationshipId: relationship.id });
    adjacency.get(relationship.target_id).push({ next: relationship.source_id, relationshipId: relationship.id });
  });

  const bridgeIds = new Set();
  for (let i = 0; i < anchorIds.length; i += 1) {
    for (let j = i + 1; j < anchorIds.length; j += 1) {
      findShortestRelationshipPath(anchorIds[i], anchorIds[j], adjacency).forEach((relationshipId) => bridgeIds.add(relationshipId));
    }
  }
  return bridgeIds;
}

function findShortestRelationshipPath(sourceId, targetId, adjacency) {
  const visited = new Set([sourceId]);
  const queue = [{ nodeId: sourceId, path: [] }];
  while (queue.length) {
    const current = queue.shift();
    if (current.nodeId === targetId) {
      return current.path;
    }
    if (current.path.length >= 4) {
      continue;
    }
    (adjacency.get(current.nodeId) || []).forEach((edge) => {
      if (visited.has(edge.next)) {
        return;
      }
      visited.add(edge.next);
      queue.push({ nodeId: edge.next, path: [...current.path, edge.relationshipId] });
    });
  }
  return [];
}

function getRelationshipColor(relationship) {
  if (graphBridgeRelationshipIds.value.has(relationship.id)) {
    return "#F59E0B";
  }
  const type = String(relationship?.type || "").toUpperCase();
  if (type.includes("NEGATIVE") || type.includes("INHIBIT")) {
    return "#EF4444";
  }
  if (type.includes("POSITIVE") || type.includes("ACTIVAT")) {
    return "#22C55E";
  }
  if (type.includes("BIND") || type.includes("INTERACT")) {
    return "#06B6D4";
  }
  if (type.includes("PARTICIPATES") || type.includes("PATHWAY")) {
    return "#8B5CF6";
  }
  return "#64748B";
}

function setupGraphCanvas() {
  resizeGraphCanvas();
  graphResizeObserver?.disconnect();
  graphResizeObserver = new ResizeObserver(() => {
    resizeGraphCanvas();
    if (graphScene.value.nodes.length) {
      rebuildGraphScene(new Set(graphScene.value.nodes.map((node) => node.id)), graphScene.value.state);
    }
  });
  if (graphCanvasStageRef.value) {
    graphResizeObserver.observe(graphCanvasStageRef.value);
  }
  drawGraphScene();
  drawGraphMinimap();
}

function resizeGraphCanvas() {
  const stage = graphCanvasStageRef.value;
  [graphCanvasRef.value, graphMinimapCanvasRef.value].forEach((canvas) => {
    if (!canvas) {
      return;
    }
    const rect = canvas === graphCanvasRef.value ? stage?.getBoundingClientRect() : canvas.getBoundingClientRect();
    const width = Math.max(1, Math.floor(rect?.width || 1));
    const height = Math.max(1, Math.floor(rect?.height || 1));
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(width * ratio);
    canvas.height = Math.floor(height * ratio);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const context = canvas.getContext("2d");
    context?.setTransform(ratio, 0, 0, ratio, 0, 0);
  });
}

function animateGraphScene(timestamp) {
  const elapsed = timestamp - graphAnimationStartedAt;
  const progress = easeOutCubic(Math.min(1, elapsed / 780));
  graphScene.value.nodes.forEach((node) => {
    node.x += (node.targetX - node.x) * Math.min(1, 0.18 + progress * 0.32);
    node.y += (node.targetY - node.y) * Math.min(1, 0.18 + progress * 0.32);
    node.opacity = Math.min(getCanvasNodeVisual(node, node.role, node.depth, node.degree).opacity, node.opacity + 0.055);
    node.scale = Math.min(1, node.scale + 0.055);
  });
  graphScene.value.relationships.forEach((relationship) => {
    relationship.progress = Math.min(1, relationship.progress + 0.045);
  });
  drawGraphScene();
  drawGraphMinimap();
  if (progress < 1 || graphScene.value.relationships.some((edge) => edge.progress < 1)) {
    graphAnimationFrame = requestAnimationFrame(animateGraphScene);
    return;
  }
  graphScene.value.state = graphAnchors.value.length > 1 ? "DualCoreStable" : graphAnchors.value.length ? "SingleCoreStable" : "Idle";
}

function easeOutCubic(value) {
  return 1 - Math.pow(1 - value, 3);
}

function drawGraphScene() {
  const canvas = graphCanvasRef.value;
  const stage = graphCanvasStageRef.value;
  if (!canvas || !stage) {
    return;
  }
  const context = canvas.getContext("2d");
  const rect = stage.getBoundingClientRect();
  context.clearRect(0, 0, rect.width, rect.height);
  drawGraphGrid(context, rect.width, rect.height);
  context.save();
  context.translate(graphViewport.value.x, graphViewport.value.y);
  context.scale(graphViewport.value.scale, graphViewport.value.scale);
  drawCanvasEdgeLayer(context);
  drawCanvasHighlightLayer(context);
  drawCanvasNodeLayer(context);
  context.restore();
}

function drawGraphMinimap() {
  const canvas = graphMinimapCanvasRef.value;
  if (!canvas) {
    return;
  }
  const context = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  context.clearRect(0, 0, rect.width, rect.height);
  context.fillStyle = "rgba(255, 255, 255, 0.78)";
  context.fillRect(0, 0, rect.width, rect.height);
  const scene = graphScene.value;
  if (!scene.nodes.length) {
    return;
  }
  const scaleX = rect.width / scene.width;
  const scaleY = rect.height / scene.height;
  context.save();
  context.globalAlpha = 0.34;
  context.strokeStyle = "#64748b";
  context.lineWidth = 1;
  scene.relationships.forEach((relationship) => {
    context.beginPath();
    context.moveTo(relationship.source.x * scaleX, relationship.source.y * scaleY);
    context.lineTo(relationship.target.x * scaleX, relationship.target.y * scaleY);
    context.stroke();
  });
  scene.nodes.forEach((node) => {
    context.fillStyle = node.fixed ? "#0f6b57" : node.color;
    context.fillRect(node.x * scaleX - 2, node.y * scaleY - 2, node.fixed ? 6 : 4, node.fixed ? 6 : 4);
  });
  const stage = graphCanvasStageRef.value;
  if (stage) {
    const viewX = Math.max(0, -graphViewport.value.x / graphViewport.value.scale);
    const viewY = Math.max(0, -graphViewport.value.y / graphViewport.value.scale);
    const viewWidth = stage.clientWidth / graphViewport.value.scale;
    const viewHeight = stage.clientHeight / graphViewport.value.scale;
    context.strokeStyle = "#f59e0b";
    context.lineWidth = 2;
    context.strokeRect(viewX * scaleX, viewY * scaleY, viewWidth * scaleX, viewHeight * scaleY);
  }
  context.restore();
}

function drawGraphGrid(context, width, height) {
  context.save();
  context.strokeStyle = "rgba(30, 41, 59, 0.055)";
  context.lineWidth = 1;
  for (let x = 0; x < width; x += 28) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y < height; y += 28) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
  context.restore();
}

function drawCanvasEdgeLayer(context) {
  const focusItem = getGraphFocusItem();
  graphScene.value.relationships.forEach((relationship) => {
    const source = relationship.source;
    const target = relationship.target;
    const progress = relationship.progress ?? 1;
    const end = {
      x: source.x + (target.x - source.x) * progress,
      y: source.y + (target.y - source.y) * progress
    };
    const dimmed = focusItem && !isCanvasRelationshipRelatedToFocus(relationship, focusItem);
    const focused = focusItem?.kind === "relationship" && focusItem.item.id === relationship.id;
    const visual = relationship.visual;
    context.save();
    context.globalAlpha = dimmed ? 0.18 : focused ? 1 : visual.opacity;
    context.strokeStyle = visual.color;
    context.lineWidth = focused ? visual.width + 2.2 : visual.width;
    if (visual.dash) {
      context.setLineDash(visual.dash);
      context.lineDashOffset = relationship.inPath ? -(performance.now() / 55) % 18 : 0;
    }
    drawCurvedEdge(context, source, end, relationship.curve || 0);
    context.restore();
  });
}

function drawCurvedEdge(context, source, target, curve) {
  const midX = (source.x + target.x) / 2;
  const midY = (source.y + target.y) / 2;
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const length = Math.hypot(dx, dy) || 1;
  const controlX = midX + (-dy / length) * curve;
  const controlY = midY + (dx / length) * curve;
  context.beginPath();
  context.moveTo(source.x, source.y);
  context.quadraticCurveTo(controlX, controlY, target.x, target.y);
  context.stroke();
}

function drawCanvasHighlightLayer(context) {
  const focusItem = getGraphFocusItem();
  if (!focusItem) {
    return;
  }
  if (focusItem.kind === "node") {
    const node = graphScene.value.nodes.find((item) => item.id === focusItem.item.id);
    if (!node) {
      return;
    }
    context.save();
    context.strokeStyle = "rgba(245, 158, 11, 0.34)";
    context.lineWidth = 2;
    context.beginPath();
    context.arc(node.x, node.y, node.radius + 15, 0, Math.PI * 2);
    context.stroke();
    context.restore();
  }
}

function drawCanvasNodeLayer(context) {
  const focusItem = getGraphFocusItem();
  graphScene.value.nodes.forEach((node) => {
    const state = resolveCanvasNodeState(node, focusItem);
    const scale = node.scale * (state === "hovered" ? 1.12 : state === "selected" ? 1.08 : 1);
    const radius = node.radius * scale;
    const alpha = state === "dimmed" ? Math.min(0.26, node.opacity) : node.opacity;
    context.save();
    context.globalAlpha = alpha;
    if (node.glow) {
      const pulse = (Math.sin(performance.now() / 230) + 1) / 2;
      context.beginPath();
      context.fillStyle = colorWithAlpha(node.color, 0.15 + pulse * 0.18);
      context.arc(node.x, node.y, radius + 8 + pulse * 8, 0, Math.PI * 2);
      context.fill();
    }
    context.beginPath();
    context.fillStyle = node.role === "bridge" ? "#fff7ed" : isCanvasSecondaryCoreRole(node.role) ? "#f8fffb" : "#ffffff";
    context.strokeStyle = state === "hovered" || state === "selected" ? "#0f172a" : node.borderColor;
    context.lineWidth = state === "hovered" || state === "selected" || node.fixed ? 3 : isCanvasSecondaryCoreRole(node.role) ? 2.4 : 1.6;
    context.arc(node.x, node.y, radius, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.beginPath();
    context.fillStyle = node.color;
    context.arc(node.x, node.y, Math.max(5, radius * 0.34), 0, Math.PI * 2);
    context.fill();
    if (node.labelVisible || node.fixed || state === "hovered" || state === "selected") {
      drawCanvasNodeLabel(context, node, radius);
    }
    context.restore();
  });
}

function drawCanvasNodeLabel(context, node, radius) {
  const label = node.fixed ? `[${node.name || node.id.slice(0, 8)}]` : node.name || node.id.slice(0, 8);
  context.font = node.fixed ? "700 13px Aptos, Segoe UI, sans-serif" : "600 12px Aptos, Segoe UI, sans-serif";
  const width = Math.min(220, Math.max(72, context.measureText(label).width + 18));
  const x = node.x - width / 2;
  const y = node.y + radius + 10;
  context.fillStyle = "rgba(255,255,255,0.92)";
  roundRect(context, x, y, width, 24, 7);
  context.fill();
  context.strokeStyle = "rgba(203,213,225,0.85)";
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = "#17201a";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillText(truncateCanvasText(label, 26), node.x, y + 12);
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.moveTo(x + radius, y);
  context.lineTo(x + width - radius, y);
  context.quadraticCurveTo(x + width, y, x + width, y + radius);
  context.lineTo(x + width, y + height - radius);
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  context.lineTo(x + radius, y + height);
  context.quadraticCurveTo(x, y + height, x, y + height - radius);
  context.lineTo(x, y + radius);
  context.quadraticCurveTo(x, y, x + radius, y);
}

function truncateCanvasText(value, maxLength) {
  const text = String(value || "");
  return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
}

function colorWithAlpha(color, alpha) {
  const hex = color.replace("#", "");
  if (hex.length !== 6) {
    return `rgba(148, 163, 184, ${alpha})`;
  }
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function resolveCanvasNodeState(node, focusItem) {
  if (graphDragState.value?.kind === "node" && graphDragState.value.nodeId === node.id) return "dragging";
  if (focusItem?.kind === "node" && focusItem.item.id === node.id) return "hovered";
  if (selectedGraphItem.value?.kind === "node" && selectedGraphItem.value.item.id === node.id) return "selected";
  if (node.fixed) return "core";
  if (focusItem && !isCanvasNodeRelatedToFocus(node, focusItem)) return "dimmed";
  if (graphScene.value.pathNodeIds?.has(node.id)) return "path";
  return "default";
}

function isCanvasNodeRelatedToFocus(node, focusItem) {
  if (!focusItem) {
    return true;
  }
  if (focusItem.kind === "relationship") {
    const relationship = focusItem.item;
    return node.id === relationship.source_id || node.id === relationship.target_id;
  }
  const activeNodeId = focusItem.item.id;
  if (node.id === activeNodeId) {
    return true;
  }
  return graphRelationships.value.some(
    (relationship) =>
      (relationship.source_id === activeNodeId && relationship.target_id === node.id) ||
      (relationship.target_id === activeNodeId && relationship.source_id === node.id)
  );
}

function isCanvasRelationshipRelatedToFocus(relationship, focusItem) {
  if (!focusItem) {
    return true;
  }
  if (focusItem.kind === "relationship") {
    return relationship.id === focusItem.item.id;
  }
  const activeNodeId = focusItem.item.id;
  return relationship.source_id === activeNodeId || relationship.target_id === activeNodeId;
}

function isGraphItemSelected(kind, item) {
  return selectedGraphItem.value?.kind === kind && selectedGraphItem.value?.item?.id === item.id;
}

function isGraphItemFocused(kind, item) {
  const focusItem = getGraphFocusItem();
  return focusItem?.kind === kind && focusItem?.item?.id === item.id;
}

function getGraphFocusItem() {
  return hoveredGraphItem.value || selectedGraphItem.value;
}

function selectGraphItem(kind, item) {
  selectedGraphItem.value = { kind, item };
  drawGraphScene();
}

function clearGraphSelection() {
  selectedGraphItem.value = null;
  hoveredGraphItem.value = null;
  graphTooltip.value = null;
  drawGraphScene();
}

function handleGraphClick(event) {
  if (suppressNextGraphClick) {
    clearGraphClickSuppressTimer();
    suppressNextGraphClick = false;
    return;
  }
  const pointer = getGraphPointer(event);
  const node = hitTestCanvasNode(pointer.worldX, pointer.worldY);
  if (node) {
    selectGraphItem("node", node);
    return;
  }
  const relationship = hitTestCanvasRelationship(pointer.worldX, pointer.worldY, 6 / graphViewport.value.scale);
  if (relationship) {
    selectGraphItem("relationship", relationship);
    return;
  }
  clearGraphSelection();
}

function handleGraphDoubleClick(event) {
  const pointer = getGraphPointer(event);
  const node = hitTestCanvasNode(pointer.worldX, pointer.worldY);
  if (node) {
    expandGraphNode(node);
  }
}

function centerGraphOn(worldX, worldY) {
  const stage = graphCanvasStageRef.value;
  if (!stage) {
    return;
  }
  graphViewport.value = {
    ...graphViewport.value,
    x: stage.clientWidth / 2 - worldX * graphViewport.value.scale,
    y: stage.clientHeight / 2 - worldY * graphViewport.value.scale
  };
}

function clearGraphNodeLongPressTimer() {
  if (graphNodeLongPressTimer) {
    clearTimeout(graphNodeLongPressTimer);
    graphNodeLongPressTimer = 0;
  }
}

function clearGraphClickSuppressTimer() {
  if (graphClickSuppressTimer) {
    clearTimeout(graphClickSuppressTimer);
    graphClickSuppressTimer = 0;
  }
}

function suppressGraphClickBriefly() {
  clearGraphClickSuppressTimer();
  suppressNextGraphClick = true;
  graphClickSuppressTimer = setTimeout(() => {
    suppressNextGraphClick = false;
    graphClickSuppressTimer = 0;
  }, 420);
}

function activateGraphNodeDrag(state) {
  if (!state || state.kind !== "pending-node") {
    return;
  }
  const hitNode = graphScene.value.nodes.find((node) => node.id === state.nodeId);
  if (!hitNode) {
    graphDragState.value = null;
    return;
  }
  cancelAnimationFrame(graphAnimationFrame);
  isGraphDragging.value = true;
  graphDragState.value = {
    kind: "node",
    nodeId: hitNode.id,
    startWorldX: state.startWorldX,
    startWorldY: state.startWorldY,
    deltaX: state.deltaX || 0,
    deltaY: state.deltaY || 0,
    released: false,
    startedAt: performance.now(),
    releasedAt: null,
    startX: hitNode.x,
    startY: hitNode.y,
    draggedNodes: createGraphSpringDragNodes(hitNode)
  };
  suppressGraphClickBriefly();
  startGraphSpringLoop();
}

function createGraphSpringDragNodes(coreNode) {
  const group = getCoreDragGroup(coreNode);
  return group.map((node, index) => {
    const isPrimary = node.id === coreNode.id;
    const isFirstHopFollower = !isPrimary && (isCanvasSecondaryCoreRole(node.role) || isNodeWithinCoreNeighborhood(coreNode.id, node.id, 1));
    const angle = getStableNodeAngle(`${coreNode.id}-${node.id}`);
    const distanceFromCore = Math.hypot(node.x - coreNode.x, node.y - coreNode.y);
    const delay = isPrimary ? 0 : isFirstHopFollower ? Math.min(90, 18 + index * 7) : Math.min(220, 45 + index * 18 + (distanceFromCore / 420) * 80);
    return {
      id: node.id,
      isPrimary,
      startX: node.x,
      startY: node.y,
      vx: 0,
      vy: 0,
      delay,
      stiffness: isPrimary ? 1 : isFirstHopFollower ? 0.18 + (Math.sin(angle) + 1) * 0.035 : 0.085 + (Math.sin(angle) + 1) * 0.025,
      damping: isPrimary ? 1 : isFirstHopFollower ? 0.62 + (Math.cos(angle) + 1) * 0.035 : 0.76 + (Math.cos(angle) + 1) * 0.045,
      reboundX: isPrimary ? 0 : Math.cos(angle) * (isFirstHopFollower ? 12 + (index % 4) * 3 : 4 + (index % 4) * 2.2),
      reboundY: isPrimary ? 0 : Math.sin(angle) * (isFirstHopFollower ? 12 + (index % 3) * 3 : 4 + (index % 3) * 2.4)
    };
  });
}

function startGraphSpringLoop() {
  if (graphSpringFrame) {
    return;
  }
  graphLastSpringAt = performance.now();
  graphSpringFrame = requestAnimationFrame(stepGraphSpringDrag);
}

function stepGraphSpringDrag(timestamp) {
  graphSpringFrame = 0;
  const state = graphDragState.value;
  if (!state?.kind || state.kind !== "node") {
    return;
  }
  const dt = Math.min(32, timestamp - graphLastSpringAt) / 16.67;
  graphLastSpringAt = timestamp;
  let moving = false;
  const elapsed = timestamp - state.startedAt;
  const releaseElapsed = state.releasedAt ? timestamp - state.releasedAt : 0;
  const reboundDecay = state.released ? Math.max(0, 1 - releaseElapsed / 520) : 0;

  state.draggedNodes.forEach((dragged) => {
    const node = graphScene.value.nodes.find((item) => item.id === dragged.id);
    if (!node) {
      return;
    }
    const delayedProgress = dragged.isPrimary ? 1 : Math.max(0, Math.min(1, (elapsed - dragged.delay) / 180));
    const easedProgress = easeOutCubic(delayedProgress);
    const targetX = dragged.startX + state.deltaX * easedProgress + dragged.reboundX * reboundDecay;
    const targetY = dragged.startY + state.deltaY * easedProgress + dragged.reboundY * reboundDecay;

    if (dragged.isPrimary) {
      node.x = dragged.startX + state.deltaX;
      node.y = dragged.startY + state.deltaY;
      node.targetX = node.x;
      node.targetY = node.y;
    } else {
      const springX = (targetX - node.x) * dragged.stiffness * dt;
      const springY = (targetY - node.y) * dragged.stiffness * dt;
      dragged.vx = (dragged.vx + springX) * Math.pow(dragged.damping, dt);
      dragged.vy = (dragged.vy + springY) * Math.pow(dragged.damping, dt);
      node.x += dragged.vx * dt;
      node.y += dragged.vy * dt;
      node.targetX = targetX;
      node.targetY = targetY;
    }

    graphNodePositions.value[node.id] = { x: node.x, y: node.y };
    if (!dragged.isPrimary && (Math.hypot(node.x - targetX, node.y - targetY) > 0.7 || Math.hypot(dragged.vx, dragged.vy) > 0.08 || delayedProgress < 1)) {
      moving = true;
    }
  });

  drawGraphScene();
  drawGraphMinimap();
  if (state.released && (!moving || releaseElapsed > 720)) {
    settleGraphSpringDrag(state);
    graphDragState.value = null;
    return;
  }
  graphSpringFrame = requestAnimationFrame(stepGraphSpringDrag);
}

function settleGraphSpringDrag(state) {
  state.draggedNodes.forEach((dragged) => {
    const node = graphScene.value.nodes.find((item) => item.id === dragged.id);
    if (!node) {
      return;
    }
    const targetX = dragged.startX + state.deltaX;
    const targetY = dragged.startY + state.deltaY;
    node.x = targetX;
    node.y = targetY;
    node.targetX = targetX;
    node.targetY = targetY;
    graphNodePositions.value[node.id] = { x: targetX, y: targetY };
  });
  drawGraphScene();
  drawGraphMinimap();
}

function releaseGraphSpringDrag(state) {
  state.released = true;
  state.releasedAt = performance.now();
  state.draggedNodes.forEach((dragged) => {
    if (!dragged.isPrimary) {
      dragged.vx += dragged.reboundX * 0.055;
      dragged.vy += dragged.reboundY * 0.055;
    }
  });
  startGraphSpringLoop();
}

function getCoreDragGroup(coreNode) {
  if (!coreNode) {
    return [];
  }
  if (isCanvasSecondaryCoreRole(coreNode.role)) {
    return graphScene.value.nodes.filter((node) => node.id === coreNode.id || node.secondaryParentId === coreNode.id);
  }
  if (!coreNode.fixed) {
    return [coreNode];
  }
  const coreRole = coreNode.role;
  const pairedCluster = coreRole === "coreA" ? "clusterA" : coreRole === "coreB" ? "clusterB" : null;
  const pairedSecondaryCore = coreRole === "coreA" ? "secondaryCoreA" : coreRole === "coreB" ? "secondaryCoreB" : null;
  const ownerCoreIndex = coreRole === "coreA" ? 0 : coreRole === "coreB" ? 1 : -1;
  const hasSingleCore = graphScene.value.nodes.filter((node) => node.fixed).length <= 1;
  return graphScene.value.nodes.filter((node) => {
    if (node.id === coreNode.id) {
      return true;
    }
    if (hasSingleCore) {
      return isNodeWithinCoreNeighborhood(coreNode.id, node.id, 2);
    }
    if (node.role === pairedSecondaryCore || node.ownerCoreIndex === ownerCoreIndex) {
      return true;
    }
    if (node.role === pairedCluster) {
      return true;
    }
    if (node.role === "bridge") {
      return isNodeWithinCoreNeighborhood(coreNode.id, node.id, 1);
    }
    return false;
  });
}

function isNodeWithinCoreNeighborhood(coreId, nodeId, maxDepth) {
  if (coreId === nodeId) {
    return true;
  }
  const adjacency = buildGraphAdjacency(graphRelationships.value);
  const visited = new Set([coreId]);
  const queue = [{ id: coreId, depth: 0 }];
  while (queue.length) {
    const current = queue.shift();
    if (current.depth >= maxDepth) {
      continue;
    }
    for (const nextId of adjacency.get(current.id) || []) {
      if (visited.has(nextId)) {
        continue;
      }
      if (nextId === nodeId) {
        return true;
      }
      visited.add(nextId);
      queue.push({ id: nextId, depth: current.depth + 1 });
    }
  }
  return false;
}

async function expandGraphNode(node) {
  if (!node?.name || graphStatus.value === "searching") {
    return;
  }
  const previousNodeIds = new Set(graphNodes.value.map((item) => item.id));
  snapshotGraphPositions();
  selectedGraphItem.value = { kind: "node", item: node };
  graphStatus.value = "searching";
  try {
    const response = await searchGraphNodes({
      name: node.name,
      depth: getGraphSearchDepth(),
      direction: "both",
      limit: graphLimit,
      include_properties: true,
      llm_text: false
    });
    graphExpansionResults.value = {
      ...graphExpansionResults.value,
      [node.id]: {
        nodes: response.nodes || response.matched_nodes || [],
        relationships: response.relationships || [],
        warnings: response.warnings || []
      }
    };
    recomputeGraphData(response.warnings || []);
    stageGraphReveal(previousNodeIds);
    await nextTick();
    rebuildGraphScene(previousNodeIds, graphAnchors.value.length > 1 ? "DualCoreTransition" : "SingleCoreLayout");
    graphStatus.value = "done";
  } catch (error) {
    graphData.value = { ...graphData.value, warnings: [error.message] };
    graphStatus.value = "error";
  }
}

function handleGraphWheel(event) {
  if (!graphNodes.value.length) {
    return;
  }
  const rect = graphCanvasStageRef.value?.getBoundingClientRect();
  if (!rect) {
    return;
  }
  const viewport = graphViewport.value;
  if (event.ctrlKey || Math.abs(event.deltaY) > Math.abs(event.deltaX)) {
    const nextScale = Math.min(2.4, Math.max(0.42, viewport.scale * (event.deltaY > 0 ? 0.9 : 1.1)));
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const scaleRatio = nextScale / viewport.scale;
    graphViewport.value = {
      scale: nextScale,
      x: pointerX - (pointerX - viewport.x) * scaleRatio,
      y: pointerY - (pointerY - viewport.y) * scaleRatio
    };
    return;
  }
  graphViewport.value = {
    ...viewport,
    x: viewport.x - event.deltaX,
    y: viewport.y - event.deltaY
  };
}

function startGraphPan(event) {
  if (event.button !== 0) {
    return;
  }
  const pointer = getGraphPointer(event);
  const hitNode = hitTestCanvasNode(pointer.worldX, pointer.worldY);
  if (hitNode) {
    clearGraphNodeLongPressTimer();
    selectedGraphItem.value = { kind: "node", item: hitNode };
    graphDragState.value = {
      kind: "pending-node",
      nodeId: hitNode.id,
      startWorldX: pointer.worldX,
      startWorldY: pointer.worldY,
      deltaX: 0,
      deltaY: 0,
      startClientX: event.clientX,
      startClientY: event.clientY,
      cancelled: false
    };
    const pendingState = graphDragState.value;
    graphNodeLongPressTimer = setTimeout(() => {
      if (graphDragState.value === pendingState && !pendingState.cancelled) {
        activateGraphNodeDrag(pendingState);
      }
    }, GRAPH_NODE_LONG_PRESS_MS);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    return;
  }
  clearGraphNodeLongPressTimer();
  isGraphDragging.value = true;
  graphDragState.value = {
    kind: "pan",
    startX: event.clientX,
    startY: event.clientY,
    viewport: { ...graphViewport.value }
  };
  event.currentTarget.setPointerCapture?.(event.pointerId);
}

function moveGraphPan(event) {
  if (!graphDragState.value) {
    updateGraphHover(event);
    return;
  }
  const state = graphDragState.value;
  if (state.kind === "pending-node") {
    const pointer = getGraphPointer(event);
    state.deltaX = pointer.worldX - state.startWorldX;
    state.deltaY = pointer.worldY - state.startWorldY;
    if (Math.hypot(event.clientX - state.startClientX, event.clientY - state.startClientY) > GRAPH_NODE_LONG_PRESS_MOVE_TOLERANCE) {
      state.startWorldX = pointer.worldX;
      state.startWorldY = pointer.worldY;
      state.deltaX = 0;
      state.deltaY = 0;
      state.startClientX = event.clientX;
      state.startClientY = event.clientY;
    }
    return;
  }
  if (state.kind === "node") {
    if (state.released) {
      return;
    }
    const pointer = getGraphPointer(event);
    state.deltaX = pointer.worldX - state.startWorldX;
    state.deltaY = pointer.worldY - state.startWorldY;
    startGraphSpringLoop();
    return;
  }
  graphViewport.value = {
    ...state.viewport,
    x: state.viewport.x + event.clientX - state.startX,
    y: state.viewport.y + event.clientY - state.startY
  };
}

function stopGraphPan(event) {
  clearGraphNodeLongPressTimer();
  if (graphDragState.value?.kind === "pending-node") {
    graphDragState.value = null;
  } else if (graphDragState.value?.kind === "node") {
    releaseGraphSpringDrag(graphDragState.value);
  } else {
    graphDragState.value = null;
  }
  isGraphDragging.value = false;
  if (event?.type === "pointerleave") {
    hoveredGraphItem.value = null;
    graphTooltip.value = null;
  }
  try {
    event.currentTarget?.releasePointerCapture?.(event.pointerId);
  } catch {
    // Pointer capture can already be released by the browser on leave/cancel.
  }
}

function updateGraphHover(event) {
  const pointer = getGraphPointer(event);
  const node = hitTestCanvasNode(pointer.worldX, pointer.worldY);
  if (node) {
    hoveredGraphItem.value = { kind: "node", item: node };
    graphTooltip.value = buildGraphTooltip("node", node, pointer.screenX, pointer.screenY);
    return;
  }
  const relationship = hitTestCanvasRelationship(pointer.worldX, pointer.worldY, 6 / graphViewport.value.scale);
  if (relationship) {
    hoveredGraphItem.value = { kind: "relationship", item: relationship };
    graphTooltip.value = buildGraphTooltip("relationship", relationship, pointer.screenX, pointer.screenY);
    return;
  }
  hoveredGraphItem.value = null;
  graphTooltip.value = null;
}

function startMinimapDrag(event) {
  isGraphMinimapDragging.value = true;
  event.currentTarget.setPointerCapture?.(event.pointerId);
  focusMinimap(event);
}

function moveMinimapDrag(event) {
  if (isGraphMinimapDragging.value) {
    focusMinimap(event);
  }
}

function stopMinimapDrag(event) {
  isGraphMinimapDragging.value = false;
  try {
    event.currentTarget?.releasePointerCapture?.(event.pointerId);
  } catch {
    // Pointer capture can already be released by the browser on leave/cancel.
  }
}

function focusMinimap(event) {
  const rect = event.currentTarget.getBoundingClientRect();
  const stage = graphCanvasStageRef.value;
  if (!stage) {
    return;
  }
  const ratioX = (event.clientX - rect.left) / rect.width;
  const ratioY = (event.clientY - rect.top) / rect.height;
  const targetX = ratioX * graphScene.value.width;
  const targetY = ratioY * graphScene.value.height;
  graphViewport.value = {
    ...graphViewport.value,
    x: stage.clientWidth / 2 - targetX * graphViewport.value.scale,
    y: stage.clientHeight / 2 - targetY * graphViewport.value.scale
  };
}

function fitGraphToView() {
  const stage = graphCanvasStageRef.value;
  const scene = graphScene.value;
  if (!stage || !scene.nodes.length) {
    return;
  }
  const bounds = getGraphContentBounds(scene.nodes);
  const canvasWidth = stage.clientWidth || 1000;
  const canvasHeight = stage.clientHeight || 620;
  const paddingRatio = 0.14;
  const availableWidth = canvasWidth * (1 - paddingRatio);
  const availableHeight = canvasHeight * (1 - paddingRatio);
  const scale = Math.min(1.05, Math.max(0.18, Math.min(availableWidth / bounds.width, availableHeight / bounds.height)));
  graphViewport.value = {
    scale,
    x: canvasWidth / 2 - bounds.centerX * scale,
    y: canvasHeight / 2 - bounds.centerY * scale
  };
}

function getGraphContentBounds(nodes) {
  const minX = Math.min(...nodes.map((node) => node.targetX - node.radius - 140));
  const maxX = Math.max(...nodes.map((node) => node.targetX + node.radius + 140));
  const minY = Math.min(...nodes.map((node) => node.targetY - node.radius - 90));
  const maxY = Math.max(...nodes.map((node) => node.targetY + node.radius + 90));
  return {
    minX,
    maxX,
    minY,
    maxY,
    width: Math.max(1, maxX - minX),
    height: Math.max(1, maxY - minY),
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2
  };
}

function getGraphPointer(event) {
  const rect = graphCanvasStageRef.value.getBoundingClientRect();
  const screenX = event.clientX - rect.left;
  const screenY = event.clientY - rect.top;
  return {
    screenX,
    screenY,
    worldX: (screenX - graphViewport.value.x) / graphViewport.value.scale,
    worldY: (screenY - graphViewport.value.y) / graphViewport.value.scale
  };
}

function hitTestCanvasNode(worldX, worldY) {
  for (let index = graphScene.value.nodes.length - 1; index >= 0; index -= 1) {
    const node = graphScene.value.nodes[index];
    if (Math.hypot(worldX - node.x, worldY - node.y) <= node.radius + 8) {
      return node;
    }
  }
  return null;
}

function hitTestCanvasRelationship(worldX, worldY, tolerance) {
  let nearest = null;
  graphScene.value.relationships.forEach((relationship) => {
    const distance = pointToSegmentDistance(worldX, worldY, relationship.source.x, relationship.source.y, relationship.target.x, relationship.target.y);
    if (distance <= tolerance && (!nearest || distance < nearest.distance)) {
      nearest = { relationship, distance };
    }
  });
  return nearest?.relationship || null;
}

function pointToSegmentDistance(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSq = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSq));
  const x = x1 + t * dx;
  const y = y1 + t * dy;
  return Math.hypot(px - x, py - y);
}

function buildGraphTooltip(kind, item, x, y) {
  const properties = graphItemProperties(item);
  const propertyEntries = Object.entries(properties).slice(0, 4);
  return {
    kind,
    x,
    y,
    title: kind === "node" ? item.name || item.id : item.type,
    subtitle: kind === "node" ? getNodeType(item) : `${item.source_name || item.source_id} -> ${item.target_name || item.target_id}`,
    properties: propertyEntries,
    degree: kind === "node" ? graphRelationships.value.filter((edge) => edge.source_id === item.id || edge.target_id === item.id).length : null
  };
}

function graphItemProperties(item) {
  return item?.properties && Object.keys(item.properties).length ? item.properties : {};
}

function formatFileSize(size) {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark"><BrainCircuit :size="22" /></div>
        <div>
          <strong>Multiomics GraphRAG</strong>
          <span>多组学科研智能体平台</span>
        </div>
      </div>

      <nav class="module-nav" aria-label="主功能模块">
        <button
          v-for="item in modules"
          :key="item.id"
          :class="{ active: activeModule === item.id }"
          type="button"
          @click="setModule(item.id)"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <main class="page">
      <header class="page-header">
        <div>
          <span class="eyebrow">科研探索工作台</span>
          <h1>{{ pageTitle }}</h1>
        </div>
      </header>

      <section v-if="activeModule === 'chat'" class="chat-page">
        <aside class="chat-session-panel" aria-label="问答会话记录">
          <div class="chat-session-heading">
            <span>会话日志</span>
            <small>悬浮滚动</small>
          </div>
          <button class="new-chat-button" type="button" @click="startNewChat">
            <Plus :size="18" />
            <span>新建问答</span>
          </button>
          <div v-if="!chatSessions.length" class="empty-state session-empty">暂无历史会话</div>
          <button
            v-for="session in chatSessions"
            :key="session.id"
            :class="{ active: activeChatSessionId === session.id }"
            type="button"
            @click="openChatSession(session.id)"
          >
            <Bot :size="16" />
            <span>{{ session.title }}</span>
            <small>{{ formatSessionTime(session) }}</small>
          </button>
        </aside>

        <div class="chat-main">
        <div ref="chatThread" class="chat-thread" aria-label="问答消息">
          <article
            v-for="message in messages"
            :key="message.id"
            :class="['chat-message', message.role === 'user' ? 'from-user' : 'from-assistant']"
          >
            <div class="avatar">
              <Bot v-if="message.role === 'assistant'" :size="17" />
              <span v-else>你</span>
            </div>
            <div class="bubble">
              <div v-if="message.attachment" class="message-attachment">
                <FileSpreadsheet :size="16" />
                <span>{{ message.attachment.name }}</span>
              </div>
              <div v-if="message.status === 'thinking'" class="thinking-indicator">
                <Loader2 :size="16" class="spin" />
                <span>思考中<span class="thinking-dots"><span>.</span><span>.</span><span>.</span></span></span>
              </div>
              <div v-else class="markdown-body" v-html="renderMarkdown(message.content)" />
            </div>
          </article>
          <div ref="messagesEnd" />
        </div>

        <footer class="composer-panel">
          <div
            v-if="chatDatasetLoadState !== 'idle'"
            :class="['dataset-load-toast', chatDatasetLoadState === 'done' ? 'is-done' : 'is-loading']"
            role="status"
            aria-live="polite"
          >
            <Loader2 v-if="chatDatasetLoadState === 'loading'" :size="16" class="spin" />
            <FileSpreadsheet v-else :size="16" />
            <span>{{ chatDatasetLoadState === "loading" ? "实验数据载入中" : "实验数据载入已完成" }}</span>
          </div>

          <div v-if="activeSessionDataset" class="session-dataset-loaded">
            <FileSpreadsheet :size="17" />
            <span>{{ activeSessionDataset.name }}实验数据已载入当前会话</span>
          </div>

          <div v-if="attachedDataset" class="attached-file">
            <FileSpreadsheet :size="17" />
            <div>
              <strong>{{ attachedDataset.name }}</strong>
              <span>{{ attachedDataset.meta }}</span>
            </div>
            <button class="icon-button flat" type="button" title="移除附件" @click="removeAttachment">
              <X :size="16" />
            </button>
          </div>

          <div class="composer">
            <div class="upload-control">
              <button
                class="icon-button"
                type="button"
                title="上传或选择实验数据"
                :disabled="isComposerLocked"
                @click="uploadMenuOpen = !uploadMenuOpen"
              >
                <Paperclip :size="18" />
              </button>

              <div v-if="uploadMenuOpen" class="upload-menu">
                <button type="button" @click="datasetPickerOpen = !datasetPickerOpen">
                  <Database :size="17" />
                  选择已有实验数据
                </button>
                <button type="button" @click="openChatFilePicker">
                  <UploadCloud :size="17" />
                  上传本地 xlsx
                </button>
              </div>
            </div>

            <textarea
              v-model="input"
              rows="1"
              placeholder="输入多组学机制问题，按 Enter 发送，Shift + Enter 换行"
              aria-label="多组学机制问题输入框"
              :disabled="isComposerLocked"
              @keydown="handleComposerKeydown"
            />

            <button class="send-button" type="button" :disabled="!input.trim() || isComposerLocked" @click="sendMessage">
              <Loader2 v-if="isSending" :size="18" class="spin" />
              <Send v-else :size="18" />
            </button>
          </div>

          <div v-if="datasetPickerOpen" class="dataset-picker">
            <button
              v-for="dataset in savedDatasets"
              :key="dataset.id"
              type="button"
              @click="selectDataset(dataset)"
            >
              <FileSpreadsheet :size="18" />
              <span>
                <strong>{{ dataset.name }}</strong>
                <small>{{ dataset.resultCount }} 个比较结果 · TOPK {{ dataset.topK }}</small>
              </span>
            </button>
            <div v-if="!savedDatasets.length" class="empty-state">暂无已解析实验数据，请先到数据处理页面上传。</div>
          </div>

          <input
            ref="chatFileInput"
            class="visually-hidden"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            @change="handleChatFile"
          />
        </footer>
        </div>
      </section>

      <section v-else-if="activeModule === 'graph'" class="graph-page">
        <div class="panel graph-toolbar">
          <div>
            <span class="eyebrow">Neo4j 知识图谱</span>
            <h2>知识图谱探索工作台</h2>
          </div>
          <div class="search-bar">
            <input
              v-model="graphQuery"
              aria-label="知识图谱搜索"
              placeholder="SMPD3;鞘脂代谢;Ceramide"
              @keyup.enter="runGraphSearch"
            />
            <label class="graph-depth-control">
              <span>跳数</span>
              <input
                v-model.number="graphDepth"
                aria-label="图谱预览跳数"
                type="number"
                min="1"
                max="5"
                step="1"
              />
            </label>
            <label class="graph-search-toggle">
              <input v-model="graphVectorSearch" type="checkbox" />
              <span>向量</span>
            </label>
            <label class="graph-search-toggle">
              <input v-model="graphRerank" type="checkbox" />
              <span>重排</span>
            </label>
            <button class="primary-button" type="button" @click="runGraphSearch">
              <Search :size="18" />
              搜索
            </button>
          </div>
        </div>

        <div v-if="graphAnchors.length" class="panel graph-anchor-panel">
          <div class="anchor-panel-title">
            <span>当前研究上下文</span>
            <button class="text-button" type="button" @click="clearGraphAnchors">清空</button>
          </div>
          <div class="anchor-tags" aria-label="图谱锚点">
            <button
              v-for="anchor in graphAnchors"
              :key="anchor.id"
              class="anchor-tag"
              type="button"
              :style="{ '--node-color': getNodeColor(anchor.node) }"
              @click="focusGraphAnchor(anchor)"
              @mouseenter="hoverGraphAnchor(anchor)"
              @mouseleave="hoveredGraphItem = null"
            >
              <component :is="getNodeIcon(anchor.node)" :size="15" />
              <span>{{ anchor.name }}</span>
              <X :size="14" class="anchor-remove" @click.stop="removeGraphAnchor(anchor.id)" />
            </button>
          </div>
        </div>

        <div class="graph-workspace">
          <div class="panel graph-canvas-panel">
            <div class="graph-statbar">
              <span>节点：{{ graphStats.nodes }}</span>
              <span>关系：{{ graphStats.relationships }}</span>
              <span>跳数：{{ graphStats.hop }}</span>
              <span>上限：{{ graphStats.limit }}</span>
              <span>布局：{{ graphStats.layout }}</span>
            </div>
            <div
              ref="graphCanvasStageRef"
              class="graph-canvas"
              :class="{ loading: graphStatus === 'searching', dragging: isGraphDragging }"
              @click="handleGraphClick"
              @dblclick="handleGraphDoubleClick"
              @wheel.prevent="handleGraphWheel"
              @pointerdown="startGraphPan"
              @pointermove="moveGraphPan"
              @pointerup="stopGraphPan"
              @pointercancel="stopGraphPan"
              @pointerleave="stopGraphPan"
            >
              <canvas ref="graphCanvasRef" class="graph-main-canvas" />
              <div v-if="!graphNodes.length && graphStatus !== 'searching'" class="graph-overview">
                <div class="overview-card">
                  <span>节点数量</span>
                  <strong>{{ graphStats.nodes }}</strong>
                </div>
                <div class="overview-card">
                  <span>关系数量</span>
                  <strong>{{ graphStats.relationships }}</strong>
                </div>
                <div class="overview-card wide">
                  <span>实体类型</span>
                  <strong>{{ graphEntityTypes.length ? graphEntityTypes.join(" / ") : "等待搜索" }}</strong>
                </div>
              </div>

              <div
                v-if="graphTooltip"
                class="graph-tooltip"
                :style="{ left: `${graphTooltip.x + 14}px`, top: `${graphTooltip.y + 14}px` }"
              >
                <strong>{{ graphTooltip.title }}</strong>
                <span>{{ graphTooltip.subtitle }}</span>
                <small v-if="graphTooltip.degree !== null">连接度：{{ graphTooltip.degree }}</small>
                <template v-for="([key, value]) in graphTooltip.properties" :key="key">
                  <small>{{ key }}: {{ value }}</small>
                </template>
              </div>

              <div v-if="graphStatus === 'searching'" class="skeleton-graph">
                <span></span>
                <span></span>
                <span></span>
              </div>

              <div
                class="graph-minimap"
                aria-hidden="true"
                @pointerdown.stop="startMinimapDrag"
                @pointermove.stop="moveMinimapDrag"
                @pointerup.stop="stopMinimapDrag"
                @pointercancel.stop="stopMinimapDrag"
              >
                <canvas ref="graphMinimapCanvasRef" />
              </div>
            </div>
            <div v-if="graphData.warnings?.length" class="warning-list">
              <AlertCircle :size="17" />
              <span>{{ graphData.warnings.join("；") }}</span>
            </div>
          </div>

          <aside class="graph-inspector">
            <div class="panel-title">
              <strong>属性详情</strong>
              <span>节点 / 关系</span>
            </div>
            <template v-if="graphDetailItem">
              <h3>
                {{ graphDetailItem.kind === "node" ? graphDetailItem.item.name : graphDetailItem.item.type }}
              </h3>
              <div v-if="graphDetailItem.kind === 'node'" class="drawer-type-pill" :style="{ '--node-color': getNodeColor(graphDetailItem.item) }">
                <component :is="getNodeIcon(graphDetailItem.item)" :size="15" />
                {{ getNodeType(graphDetailItem.item) }}
              </div>
              <p v-if="graphDetailItem.kind === 'relationship'">
                {{ graphDetailItem.item.source_name || graphDetailItem.item.source_id }}
                →
                {{ graphDetailItem.item.target_name || graphDetailItem.item.target_id }}
              </p>
              <div class="drawer-section-title">属性</div>
              <dl>
                <template v-for="(value, key) in graphItemProperties(graphDetailItem.item)" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ value }}</dd>
                </template>
              </dl>
              <div class="drawer-section-title">统计</div>
              <div class="drawer-metric-grid">
                <span>{{ graphDetailItem.kind === "node" ? "连接度" : "关系类型" }}</span>
                <strong>
                  {{
                    graphDetailItem.kind === "node"
                      ? graphRelationships.filter((item) => item.source_id === graphDetailItem.item.id || item.target_id === graphDetailItem.item.id).length
                      : graphDetailItem.item.type
                  }}
                </strong>
              </div>
              <div v-if="!Object.keys(graphItemProperties(graphDetailItem.item)).length" class="empty-state">
                该项没有返回属性信息。
              </div>
            </template>
            <div v-else class="empty-state">移动到节点或边上查看属性。</div>
          </aside>
        </div>

      </section>

      <section v-else class="datasets-page">
        <div class="panel upload-panel">
          <div>
            <span class="eyebrow">实验数据解析</span>
            <h2>上传并解析多组学实验数据</h2>
          </div>
          <div class="upload-actions">
            <label class="upload-field">
              xlsx 文件
              <button class="primary-button dataset-file-button" type="button" @click="chooseDatasetFile">
                <UploadCloud :size="18" />
                选择 xlsx
              </button>
            </label>
            <label class="upload-field">
              返回 TOPK
              <input v-model.number="datasetTopK" type="number" min="1" max="1000" />
            </label>
            <label class="upload-field dataset-name-field">
              实验数据名称
              <input v-model="datasetDisplayName" type="text" placeholder="例如：SMPD3 干预组转录组" />
            </label>
            <button class="primary-button dataset-save-button" type="button" :disabled="isParsingDataset" @click="parseSelectedDataset">
              <Loader2 v-if="isParsingDataset" :size="18" class="spin" />
              <FileSpreadsheet v-else :size="18" />
              解析保存
            </button>
          </div>
          <div v-if="selectedDatasetFile" class="selected-file">
            <FileSpreadsheet :size="17" />
            <span>{{ selectedDatasetFile.name }} · {{ formatFileSize(selectedDatasetFile.size) }}</span>
          </div>
          <div v-if="datasetStatus.message" :class="['status-message', datasetStatus.type]">
            {{ datasetStatus.message }}
          </div>
          <input
            ref="datasetFileInput"
            class="visually-hidden"
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            @change="handleDatasetFile"
          />
        </div>

        <div class="datasets-workspace">
          <div class="panel dataset-list-panel">
            <div class="panel-title">
              <strong>已解析实验数据</strong>
              <span>{{ datasets.length }} 组数据</span>
            </div>
            <table v-if="datasets.length">
              <thead>
                <tr>
                  <th>实验数据名称</th>
                  <th>原始文件</th>
                  <th>TOPK</th>
                  <th>结果数</th>
                  <th>时间</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="dataset in datasets" :key="dataset.id" :class="{ selected: previewDatasetId === dataset.id }">
                  <td>
                    <div v-if="editingDatasetId === dataset.id" class="dataset-name-edit">
                      <input v-model="editingDatasetName" type="text" @keydown.enter="renameDataset(dataset.id)" />
                      <button class="text-button" type="button" @click="renameDataset(dataset.id)">保存</button>
                      <button class="text-button muted" type="button" @click="cancelRenameDataset">取消</button>
                    </div>
                    <template v-else>
                      <div class="dataset-name-line">
                        <strong>{{ getDatasetDisplayName(dataset) }}</strong>
                        <button class="dataset-rename-button" type="button" title="更名" @click="startRenameDataset(dataset)">
                          <PencilLine :size="14" />
                        </button>
                      </div>
                      <span v-if="dataset.warnings?.length">{{ dataset.warnings.length }} 条 warning</span>
                    </template>
                  </td>
                  <td>{{ dataset.fileName || "-" }}</td>
                  <td>{{ dataset.topK }}</td>
                  <td>{{ dataset.resultCount }}</td>
                  <td>{{ formatDate(dataset.createdAt) }}</td>
                  <td>
                    <div class="dataset-row-actions">
                      <button class="text-button" type="button" @click="previewDatasetDetails(dataset)">预览</button>
                      <button class="icon-button danger" type="button" title="删除" @click="deleteDataset(dataset.id)">
                        <Trash2 :size="16" />
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="empty-state">暂无已解析数据。</div>
          </div>

          <aside class="panel dataset-preview-panel">
            <div class="panel-title">
              <strong>数据预览</strong>
              <span v-if="previewDataset">{{ previewDataset.resultCount }} 个结果</span>
            </div>
            <template v-if="previewDataset">
              <h3>{{ getDatasetDisplayName(previewDataset) }}</h3>
              <dl class="dataset-preview-meta">
                <dt>原始文件</dt>
                <dd>{{ previewDataset.fileName || "-" }}</dd>
                <dt>TOPK</dt>
                <dd>{{ previewDataset.topK }}</dd>
                <dt>文件大小</dt>
                <dd>{{ formatFileSize(previewDataset.size) }}</dd>
              </dl>
              <div v-if="Object.keys(previewDataset.groupDescriptions || {}).length" class="dataset-preview-section">
                <strong>实验分组</strong>
                <div class="dataset-chip-list">
                  <span v-for="(description, group) in previewDataset.groupDescriptions" :key="group">
                    {{ group }}: {{ description || "无描述" }}
                  </span>
                </div>
              </div>
              <div class="dataset-preview-section">
                <strong>比较结果</strong>
                <div class="dataset-chip-list">
                  <span v-for="result in previewDataset.results.slice(0, 8)" :key="getDatasetResultLabel(result)">
                    {{ getDatasetResultLabel(result) }}
                  </span>
                </div>
              </div>
              <table v-if="getDatasetPreviewRows(previewDataset).length" class="dataset-preview-table">
                <thead>
                  <tr>
                    <th>组学类型</th>
                    <th>比较组</th>
                    <th>Feature</th>
                    <th>log2FC</th>
                    <th>P adj</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(row, index) in getDatasetPreviewRows(previewDataset)" :key="row.omicsType + '-' + row.comparison + '-' + row.feature + '-' + index">
                    <td>{{ row.omicsType }}</td>
                    <td>{{ row.comparison }}</td>
                    <td>{{ row.feature }}</td>
                    <td>{{ row.log2fc != null ? formatNumber(row.log2fc) : "-" }}</td>
                    <td>{{ row.p_adjusted != null ? formatNumber(row.p_adjusted) : "-" }}</td>
                  </tr>
                </tbody>
              </table>
              <div v-else class="empty-state">该数据暂无可预览的 TOP features。</div>
            </template>
            <div v-else class="empty-state">选择一条实验数据后查看预览。</div>
          </aside>
        </div>

        <div v-if="datasetPreviewOpen && previewDataset" class="dataset-preview-overlay" @click.self="closeDatasetPreview">
          <section class="panel dataset-preview-modal" role="dialog" aria-modal="true" aria-label="实验数据预览">
            <div class="panel-title">
              <strong>数据预览</strong>
              <button class="icon-button flat" type="button" title="关闭" @click="closeDatasetPreview">
                <X :size="16" />
              </button>
            </div>
            <h3>{{ getDatasetDisplayName(previewDataset) }}</h3>
            <dl class="dataset-preview-meta">
              <dt>原始文件</dt>
              <dd>{{ previewDataset.fileName || "-" }}</dd>
              <dt>TOPK</dt>
              <dd>{{ previewDataset.topK }}</dd>
              <dt>文件大小</dt>
              <dd>{{ formatFileSize(previewDataset.size) }}</dd>
              <dt>结果数</dt>
              <dd>{{ previewDataset.resultCount }}</dd>
            </dl>
            <div v-if="Object.keys(previewDataset.groupDescriptions || {}).length" class="dataset-preview-section">
              <strong>实验分组</strong>
              <div class="dataset-chip-list">
                <span v-for="(description, group) in previewDataset.groupDescriptions" :key="group">
                  {{ group }}: {{ description || "无描述" }}
                </span>
              </div>
            </div>
            <div class="dataset-preview-section">
              <strong>比较结果分组</strong>
              <div class="dataset-group-buttons" role="tablist" aria-label="比较结果分组">
                <button
                  v-for="group in previewDatasetGroups"
                  :key="group.id"
                  :class="{ active: activeDatasetPreviewGroup?.id === group.id }"
                  type="button"
                  role="tab"
                  :aria-selected="activeDatasetPreviewGroup?.id === group.id"
                  @click="selectDatasetPreviewGroup(group.id)"
                >
                  <span>{{ group.label }}</span>
                  <small>{{ group.rows.length }} 行</small>
                </button>
              </div>
            </div>
            <div v-if="activeDatasetPreviewGroup" class="dataset-preview-groups">
              <section class="dataset-preview-group">
                <div class="dataset-preview-group-title">
                  <strong>{{ activeDatasetPreviewGroup.label }}</strong>
                  <span>按 P 值升序 · {{ activeDatasetPreviewGroup.rows.length }} 行</span>
                </div>
                <table v-if="activeDatasetPreviewGroup.rows.length" class="dataset-preview-table">
                  <thead>
                    <tr>
                      <th>特征</th>
                      <th>log2FC</th>
                      <th>Fold change</th>
                      <th>P 值</th>
                      <th>P adj</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, index) in activeDatasetPreviewGroup.rows" :key="activeDatasetPreviewGroup.id + '-' + row.feature + '-' + index">
                      <td>{{ row.feature }}</td>
                      <td>{{ row.log2fc != null ? formatNumber(row.log2fc) : "-" }}</td>
                      <td>{{ row.fold_change != null ? formatNumber(row.fold_change) : "-" }}</td>
                      <td>{{ row.p_value != null ? formatNumber(row.p_value) : "-" }}</td>
                      <td>{{ row.p_adjusted != null ? formatNumber(row.p_adjusted) : "-" }}</td>
                    </tr>
                  </tbody>
                </table>
                <div v-else class="empty-state">该分组暂无可预览的 TOP features。</div>
              </section>
            </div>
            <div v-else class="empty-state">该数据暂无可预览的 TOP features。</div>
          </section>
        </div>
      </section>
    </main>
  </div>
</template>
