#!/usr/bin/env -S npm exec --yes --package=tsx -- tsx
/**
 * Source-derived Card 2.0 schema validator.
 *
 * This is the structural layer copied from the supplied lark-card-studio
 * source and kept separate from validate_card.py.  validate_card.py remains
 * the mandatory public-safety layer for real actions, placeholders, remote
 * surfaces, and image provenance.
 */
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

type JsonValue =
    | null
    | boolean
    | number
    | string
    | JsonValue[]
    | { [key: string]: JsonValue };

type JsonObject = { [key: string]: JsonValue };

type ValidationIssue = {
  path: string;
  property?: string;
  keyword: string;
  message: string;
  schemaPath?: string;
  expected?: string;
  actual?: string;
  allowedValues?: JsonValue[];
};

type CliOptions = {
  cardPath?: string;
  jsonOutput: boolean;
  schemaPath: string;
  showHelp: boolean;
};

type CardTarget = {
  card: JsonValue;
  mode: "card" | "cardkit" | "webhook" | "openapi" | "wrapper";
  basePath: string;
};

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const DEFAULT_SCHEMA_PATH = resolve(SCRIPT_DIR, "../references/card-schema.json");

function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseArgs(argv: string[]): CliOptions {
  const options: CliOptions = {
    jsonOutput: false,
    schemaPath: process.env.LARK_CARD_SCHEMA
        ? resolve(process.env.LARK_CARD_SCHEMA)
        : DEFAULT_SCHEMA_PATH,
    showHelp: false,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "-h" || arg === "--help") {
      options.showHelp = true;
      continue;
    }

    if (arg === "--json") {
      options.jsonOutput = true;
      continue;
    }

    if (arg === "--schema") {
      const schemaPath = argv[index + 1];
      if (!schemaPath) {
        throw new Error("--schema 需要提供 schema 文件路径");
      }
      options.schemaPath = resolve(schemaPath);
      index += 1;
      continue;
    }

    if (arg.startsWith("--schema=")) {
      options.schemaPath = resolve(arg.slice("--schema=".length));
      continue;
    }

    if (arg.startsWith("-")) {
      throw new Error(`未知参数：${arg}`);
    }

    if (options.cardPath) {
      throw new Error(`只能提供一个卡片 JSON 文件路径，收到多余参数：${arg}`);
    }
    options.cardPath = arg;
  }

  return options;
}

function printHelp(): void {
  console.log(`用法：validate_card.ts [--schema <schema.json>] [--json] [card.json]

校验飞书/Lark Card JSON。未提供 card.json 时从 stdin 读取。

schema 校验通过后额外检查四条通用规范（keyword 以 houseRule/ 开头）：
  - column.weight 必须是 1，分栏一律 1:1 等分
  - Markdown 表格每列必须左对齐，禁止 ---: 和 :---:
  - collapsible_panel 必须配置统一的折叠箭头 icon（down_outlined / grey / right / -180）
  - 图标 img（size <= 48px）必须直接放在带边框 + 非默认 background_style 的 interactive_container 图标底座里

参数：
  --schema <path>  使用指定 JSON Schema；默认使用相对本脚本的 ../references/card-schema.json
  --json           以 JSON 输出校验结果，包含 errors[].path/property/keyword
  -h, --help       显示帮助

环境变量：
  LARK_CARD_SCHEMA 可覆盖默认 schema 路径`);
}

function loadJson(path: string | undefined, label: string): JsonValue {
  const raw = path ? readFileSync(path, "utf8") : readFileSync(0, "utf8");

  try {
    return JSON.parse(raw) as JsonValue;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`${label} 不是有效 JSON：${message}`);
  }
}

function appendPath(path: string, property: string | number): string {
  if (typeof property === "number") {
    return `${path}[${property}]`;
  }

  if (/^[A-Za-z_$][0-9A-Za-z_$]*$/.test(property)) {
    return `${path}.${property}`;
  }

  return `${path}[${JSON.stringify(property)}]`;
}

function appendSchemaPath(schemaPath: string, property: string | number): string {
  return `${schemaPath}/${String(property).replace(/~/g, "~0").replace(/\//g, "~1")}`;
}

function pathProperty(path: string): string | undefined {
  const dotMatch = /\.([A-Za-z_$][0-9A-Za-z_$]*)$/.exec(path);
  if (dotMatch) {
    return dotMatch[1];
  }

  const quotedMatch = /\[("(?:\\.|[^"\\])*")\]$/.exec(path);
  if (quotedMatch) {
    try {
      const value = JSON.parse(quotedMatch[1]) as unknown;
      return typeof value === "string" ? value : undefined;
    } catch {
      return undefined;
    }
  }

  return undefined;
}

function makeIssue(
    path: string,
    keyword: string,
    message: string,
    overrides: Partial<ValidationIssue> = {},
): ValidationIssue {
  return {
    path,
    property: pathProperty(path),
    keyword,
    message,
    ...overrides,
  };
}

function actualType(value: JsonValue): string {
  if (value === null) {
    return "null";
  }
  if (Array.isArray(value)) {
    return "array";
  }
  return typeof value;
}

function expectedTypes(schema: JsonObject): string[] | undefined {
  const typeKeyword = schema.type;
  if (typeof typeKeyword === "string") {
    return [typeKeyword];
  }
  if (Array.isArray(typeKeyword) && typeKeyword.every((item) => typeof item === "string")) {
    return typeKeyword as string[];
  }
  return undefined;
}

function typeMatches(value: JsonValue, expected: string): boolean {
  if (expected === "integer") {
    return typeof value === "number" && Number.isInteger(value);
  }
  return actualType(value) === expected;
}

function jsonEquals(left: JsonValue, right: JsonValue): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function formatJson(value: JsonValue): string {
  return JSON.stringify(value);
}

function formatAllowed(values: JsonValue[]): string {
  return values.map(formatJson).join(", ");
}

function issueKey(issue: ValidationIssue): string {
  return [
    issue.path,
    issue.property ?? "",
    issue.keyword,
    issue.message,
    issue.schemaPath ?? "",
  ].join("\0");
}

function dedupeIssues(issues: ValidationIssue[]): ValidationIssue[] {
  const seen = new Set<string>();
  const output: ValidationIssue[] = [];
  for (const issue of issues) {
    const key = issueKey(issue);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    output.push(issue);
  }
  return output;
}

function parseWrapper(data: JsonValue): { target: CardTarget; issues: ValidationIssue[] } {
  const issues: ValidationIssue[] = [];

  if (!isRecord(data)) {
    issues.push(makeIssue("$", "type", "顶层值必须是对象", { expected: "object", actual: actualType(data) }));
    return { target: { card: data, mode: "card", basePath: "$" }, issues };
  }

  // CardKit editor exports use the same {name, dsl, variables} envelope as
  // this repository's .cardkit.card artifact.  Validate the DSL itself.
  if ("dsl" in data) {
    return { target: { card: data.dsl, mode: "cardkit", basePath: "$.dsl" }, issues };
  }

  if (data.msg_type !== "interactive") {
    return { target: { card: data, mode: "card", basePath: "$" }, issues };
  }

  if ("card" in data) {
    return { target: { card: data.card, mode: "webhook", basePath: "$.card" }, issues };
  }

  if ("content" in data) {
    const { content } = data;
    if (typeof content !== "string") {
      issues.push(
          makeIssue("$.content", "type", "OpenAPI content 必须是序列化后的卡片 JSON 字符串", {
            property: "content",
            expected: "string",
            actual: actualType(content),
          }),
      );
      return { target: { card: content, mode: "openapi", basePath: "$.content" }, issues };
    }

    try {
      return {
        target: {
          card: JSON.parse(content) as JsonValue,
          mode: "openapi",
          basePath: "$.content",
        },
        issues,
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      issues.push(
          makeIssue("$.content", "parse", `content 不是有效的序列化卡片 JSON：${message}`, {
            property: "content",
          }),
      );
      return { target: { card: content, mode: "openapi", basePath: "$.content" }, issues };
    }
  }

  issues.push(
      makeIssue("$", "required", "interactive 外层请求体必须包含 card 或 content", {
        property: "card|content",
      }),
  );
  return { target: { card: data, mode: "wrapper", basePath: "$" }, issues };
}

class SchemaValidator {
  private readonly root: JsonObject;

  constructor(root: JsonValue) {
    if (!isRecord(root)) {
      throw new Error("schema 顶层必须是对象");
    }
    this.root = root;
  }

  validate(value: JsonValue, path = "$", schema: JsonValue = this.root, schemaPath = "#"): ValidationIssue[] {
    return dedupeIssues(this.validateNode(value, schema, path, schemaPath));
  }

  private validateNode(
      value: JsonValue,
      schemaValue: JsonValue,
      path: string,
      schemaPath: string,
  ): ValidationIssue[] {
    if (schemaValue === true) {
      return [];
    }

    if (schemaValue === false) {
      return [makeIssue(path, "falseSchema", "该位置不允许出现任何值", { schemaPath })];
    }

    if (!isRecord(schemaValue)) {
      return [];
    }

    const ref = schemaValue.$ref;
    if (typeof ref === "string") {
      const resolved = this.resolveRef(ref);
      return this.validateNode(value, resolved.schema, path, resolved.schemaPath);
    }

    const oneOf = schemaValue.oneOf;
    if (Array.isArray(oneOf)) {
      return this.validateOneOf(value, oneOf, path, appendSchemaPath(schemaPath, "oneOf"));
    }

    const issues: ValidationIssue[] = [];
    const types = expectedTypes(schemaValue);
    if (types) {
      const matches = types.some((type) => typeMatches(value, type));
      if (!matches) {
        issues.push(
            makeIssue(path, "type", `类型必须是 ${types.join(" 或 ")}，实际是 ${actualType(value)}`, {
              schemaPath: appendSchemaPath(schemaPath, "type"),
              expected: types.join("|"),
              actual: actualType(value),
            }),
        );
        return issues;
      }
    }

    if ("const" in schemaValue && !jsonEquals(value, schemaValue.const)) {
      issues.push(
          makeIssue(path, "const", `值必须等于 ${formatJson(schemaValue.const)}`, {
            schemaPath: appendSchemaPath(schemaPath, "const"),
            expected: formatJson(schemaValue.const),
            actual: formatJson(value),
          }),
      );
    }

    if (Array.isArray(schemaValue.enum) && !schemaValue.enum.some((item) => jsonEquals(value, item))) {
      issues.push(
          makeIssue(path, "enum", `值必须是以下之一：${formatAllowed(schemaValue.enum)}`, {
            schemaPath: appendSchemaPath(schemaPath, "enum"),
            allowedValues: schemaValue.enum,
            actual: formatJson(value),
          }),
      );
    }

    if (isRecord(value)) {
      issues.push(...this.validateObject(value, schemaValue, path, schemaPath));
    }

    if (Array.isArray(value)) {
      issues.push(...this.validateArray(value, schemaValue, path, schemaPath));
    }

    return issues;
  }

  private validateObject(
      value: JsonObject,
      schema: JsonObject,
      path: string,
      schemaPath: string,
  ): ValidationIssue[] {
    const issues: ValidationIssue[] = [];
    const properties = isRecord(schema.properties) ? schema.properties : undefined;
    const required = Array.isArray(schema.required)
        ? schema.required.filter((item): item is string => typeof item === "string")
        : [];

    for (const property of required) {
      if (!Object.prototype.hasOwnProperty.call(value, property)) {
        issues.push(
            makeIssue(appendPath(path, property), "required", `缺少必填属性 ${property}`, {
              property,
              schemaPath: appendSchemaPath(schemaPath, "required"),
            }),
        );
      }
    }

    if (properties) {
      for (const [property, propertySchema] of Object.entries(properties)) {
        if (!Object.prototype.hasOwnProperty.call(value, property)) {
          continue;
        }
        issues.push(
            ...this.validateNode(
                value[property],
                propertySchema,
                appendPath(path, property),
                appendSchemaPath(appendSchemaPath(schemaPath, "properties"), property),
            ),
        );
      }
    }

    if (schema.additionalProperties === false) {
      for (const property of Object.keys(value)) {
        if (properties && Object.prototype.hasOwnProperty.call(properties, property)) {
          continue;
        }
        issues.push(
            makeIssue(appendPath(path, property), "additionalProperties", `不允许出现额外属性 ${property}`, {
              property,
              schemaPath: appendSchemaPath(schemaPath, "additionalProperties"),
            }),
        );
      }
    } else if (isRecord(schema.additionalProperties)) {
      for (const property of Object.keys(value)) {
        if (properties && Object.prototype.hasOwnProperty.call(properties, property)) {
          continue;
        }
        issues.push(
            ...this.validateNode(
                value[property],
                schema.additionalProperties,
                appendPath(path, property),
                appendSchemaPath(schemaPath, "additionalProperties"),
            ),
        );
      }
    }

    return issues;
  }

  private validateArray(
      value: JsonValue[],
      schema: JsonObject,
      path: string,
      schemaPath: string,
  ): ValidationIssue[] {
    if (!isRecord(schema.items)) {
      return [];
    }

    const issues: ValidationIssue[] = [];
    value.forEach((item, index) => {
      issues.push(
          ...this.validateNode(item, schema.items, appendPath(path, index), appendSchemaPath(schemaPath, "items")),
      );
    });
    return issues;
  }

  private validateOneOf(
      value: JsonValue,
      branches: JsonValue[],
      path: string,
      schemaPath: string,
  ): ValidationIssue[] {
    const allowedTags = this.collectConstPropertyValues(branches, "tag");
    if (
        isRecord(value) &&
        typeof value.tag === "string" &&
        allowedTags.length > 0 &&
        !allowedTags.some((tag) => jsonEquals(tag, value.tag))
    ) {
      return [
        makeIssue(appendPath(path, "tag"), "oneOf", `无法匹配组件 tag ${formatJson(value.tag)}；支持：${allowedTags.join(", ")}`, {
          property: "tag",
          schemaPath,
          allowedValues: allowedTags,
          actual: formatJson(value.tag),
        }),
      ];
    }

    const selectedIndex = this.selectBranch(value, branches);
    if (selectedIndex !== undefined) {
      return this.validateNode(
          value,
          branches[selectedIndex],
          path,
          appendSchemaPath(schemaPath, selectedIndex),
      );
    }

    const results = branches.map((branch, index) => ({
      index,
      branch,
      issues: this.validateNode(value, branch, path, appendSchemaPath(schemaPath, index)),
    }));

    const validResults = results.filter((result) => result.issues.length === 0);
    if (validResults.length > 0) {
      // The card schema uses oneOf to model unions. Some branches are not fully
      // discriminated, so accepting one-or-more matches gives practical union
      // behavior while still using the schema's branch definitions.
      return [];
    }

    const best = this.bestResult(results, value);
    if (best && best.issues.length > 0) {
      return best.issues;
    }

    return [
      makeIssue(path, "oneOf", "必须匹配 schema 的其中一个分支", {
        schemaPath,
      }),
    ];
  }

  private selectBranch(value: JsonValue, branches: JsonValue[]): number | undefined {
    if (!isRecord(value)) {
      return undefined;
    }

    const tag = typeof value.tag === "string" ? value.tag : undefined;
    if (tag) {
      const matches = branches
          .map((branch, index) => ({ index, constValue: this.constProperty(branch, "tag") }))
          .filter((branch): branch is { index: number; constValue: JsonValue } => branch.constValue === tag);
      if (matches.length === 1) {
        return matches[0].index;
      }
    }

    const type = typeof value.type === "string" ? value.type : undefined;
    if (type) {
      const normalizedType = normalizeName(type);
      const titleMatches = branches
          .map((branch, index) => ({ index, title: this.branchTitle(branch) }))
          .filter(({ title }) => title && normalizeName(title).includes(normalizedType));
      if (titleMatches.length === 1) {
        return titleMatches[0].index;
      }
    }

    const scored = branches.map((branch, index) => ({
      index,
      score: this.branchPropertyScore(value, branch),
    }));
    scored.sort((left, right) => right.score - left.score);
    if (scored[0] && scored[0].score > 0 && scored[0].score > (scored[1]?.score ?? -Infinity)) {
      return scored[0].index;
    }

    return undefined;
  }

  private bestResult(
      results: Array<{ index: number; branch: JsonValue; issues: ValidationIssue[] }>,
      value: JsonValue,
  ): { index: number; branch: JsonValue; issues: ValidationIssue[] } | undefined {
    const sorted = [...results].sort((left, right) => {
      const leftWeight = this.issueWeight(left.issues) - this.branchPropertyScore(value, left.branch);
      const rightWeight = this.issueWeight(right.issues) - this.branchPropertyScore(value, right.branch);
      return leftWeight - rightWeight;
    });
    return sorted[0];
  }

  private issueWeight(issues: ValidationIssue[]): number {
    return issues.reduce((total, issue) => {
      if (issue.keyword === "const" && issue.property === "tag") {
        return total + 10;
      }
      if (issue.keyword === "additionalProperties") {
        return total + 6;
      }
      if (issue.keyword === "type" || issue.keyword === "enum" || issue.keyword === "const") {
        return total + 4;
      }
      if (issue.keyword === "required") {
        return total + 2;
      }
      return total + 1;
    }, 0);
  }

  private branchPropertyScore(value: JsonValue, branch: JsonValue): number {
    if (!isRecord(value)) {
      return 0;
    }

    const dereferenced = this.dereference(branch);
    const schema = dereferenced.schema;
    if (!isRecord(schema) || !isRecord(schema.properties)) {
      return 0;
    }

    let score = 0;
    for (const key of Object.keys(value)) {
      if (Object.prototype.hasOwnProperty.call(schema.properties, key)) {
        score += key === "tag" || key === "type" ? 2 : 4;
      } else {
        score -= 3;
      }
    }

    const required = Array.isArray(schema.required)
        ? schema.required.filter((item): item is string => typeof item === "string")
        : [];
    for (const key of required) {
      if (Object.prototype.hasOwnProperty.call(value, key)) {
        score += 1;
      }
    }

    return score;
  }

  private collectConstPropertyValues(branches: JsonValue[], property: string): JsonValue[] {
    const values: JsonValue[] = [];
    for (const branch of branches) {
      const constValue = this.constProperty(branch, property);
      if (constValue !== undefined && !values.some((value) => jsonEquals(value, constValue))) {
        values.push(constValue);
      }
    }
    return values.sort((left, right) => String(left).localeCompare(String(right)));
  }

  private constProperty(branch: JsonValue, property: string): JsonValue | undefined {
    const dereferenced = this.dereference(branch);
    const schema = dereferenced.schema;
    if (!isRecord(schema) || !isRecord(schema.properties)) {
      return undefined;
    }
    const propertySchema = schema.properties[property];
    if (!isRecord(propertySchema) || !("const" in propertySchema)) {
      return undefined;
    }
    return propertySchema.const;
  }

  private branchTitle(branch: JsonValue): string | undefined {
    const dereferenced = this.dereference(branch);
    return isRecord(dereferenced.schema) && typeof dereferenced.schema.title === "string"
        ? dereferenced.schema.title
        : undefined;
  }

  private dereference(schema: JsonValue): { schema: JsonValue; schemaPath: string } {
    if (!isRecord(schema) || typeof schema.$ref !== "string") {
      return { schema, schemaPath: "#" };
    }
    return this.resolveRef(schema.$ref);
  }

  private resolveRef(ref: string): { schema: JsonValue; schemaPath: string } {
    if (!ref.startsWith("#")) {
      throw new Error(`暂不支持外部 schema 引用：${ref}`);
    }

    if (ref === "#") {
      return { schema: this.root, schemaPath: "#" };
    }

    const pointer = ref.slice(2);
    const parts = pointer
        ? pointer.split("/").map((part) => part.replace(/~1/g, "/").replace(/~0/g, "~"))
        : [];

    let current: JsonValue = this.root;
    let schemaPath = "#";
    for (const part of parts) {
      if (!isRecord(current) && !Array.isArray(current)) {
        throw new Error(`schema 引用无效：${ref}`);
      }

      const next = (current as JsonObject | JsonValue[])[part as keyof (JsonObject | JsonValue[])];
      if (next === undefined) {
        throw new Error(`schema 引用不存在：${ref}`);
      }
      current = next;
      schemaPath = appendSchemaPath(schemaPath, part);
    }

    return { schema: current, schemaPath };
  }
}

function normalizeName(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

// 分隔行形如 | :--- | ---: |，只有 :--- 和 --- 渲染为左对齐
const TABLE_DELIMITER_ROW = /^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$/;

function nonLeftAlignedColumns(delimiterRow: string): number[] {
  const cells = delimiterRow.trim().replace(/^\|/, "").replace(/\|$/, "").split("|");
  const offenders: number[] = [];
  cells.forEach((cell, index) => {
    if (/-:\s*$/.test(cell)) {
      offenders.push(index + 1);
    }
  });
  return offenders;
}

function checkMarkdownTables(content: string, path: string): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  for (const line of content.split("\n")) {
    if (!TABLE_DELIMITER_ROW.test(line)) {
      continue;
    }
    const offenders = nonLeftAlignedColumns(line);
    if (offenders.length > 0) {
      issues.push(
          makeIssue(
              path,
              "houseRule/tableAlign",
              `Markdown 表格第 ${offenders.join("、")} 列不是左对齐；所有列的分隔行必须写成 :--- ，禁止 ---: 和 :---:`,
              { actual: line.trim() },
          ),
      );
    }
  }
  return issues;
}

// 折叠面板箭头 icon 的唯一合法形态，所有主题共用
const COLLAPSIBLE_PANEL_ICON: Record<string, string> = {
  tag: "standard_icon",
  token: "down_outlined",
  color: "grey",
};
const COLLAPSIBLE_PANEL_ICON_POSITION = "right";
const COLLAPSIBLE_PANEL_ICON_EXPANDED_ANGLE = -180;
const COLLAPSIBLE_PANEL_ICON_SNIPPET =
    '"icon": { "tag": "standard_icon", "token": "down_outlined", "color": "grey" }, "icon_position": "right", "icon_expanded_angle": -180';

function collapsiblePanelIconIssue(path: string, message: string, overrides: Partial<ValidationIssue> = {}): ValidationIssue {
  return makeIssue(path, "houseRule/collapsiblePanelIcon", `${message}；折叠面板的 header 必须写成 ${COLLAPSIBLE_PANEL_ICON_SNIPPET}`, overrides);
}

function checkCollapsiblePanelIcon(panel: JsonObject, path: string): ValidationIssue[] {
  const headerPath = appendPath(path, "header");
  if (!isRecord(panel.header)) {
    return [collapsiblePanelIconIssue(headerPath, "折叠面板缺少 header，无法配置折叠箭头 icon")];
  }

  const header = panel.header;
  const issues: ValidationIssue[] = [];
  const iconPath = appendPath(headerPath, "icon");

  if (!isRecord(header.icon)) {
    issues.push(
        collapsiblePanelIconIssue(iconPath, "折叠面板缺少 header.icon", {
          expected: formatJson(COLLAPSIBLE_PANEL_ICON),
          actual: header.icon === undefined ? "undefined" : formatJson(header.icon),
        }),
    );
  } else {
    for (const [field, expected] of Object.entries(COLLAPSIBLE_PANEL_ICON)) {
      const actual = header.icon[field];
      if (actual !== expected) {
        issues.push(
            collapsiblePanelIconIssue(appendPath(iconPath, field), `折叠面板 icon.${field} 必须是 ${formatJson(expected)}`, {
              expected: formatJson(expected),
              actual: actual === undefined ? "undefined" : formatJson(actual),
            }),
        );
      }
    }
  }

  if (header.icon_position !== COLLAPSIBLE_PANEL_ICON_POSITION) {
    issues.push(
        collapsiblePanelIconIssue(
            appendPath(headerPath, "icon_position"),
            `折叠面板 icon_position 必须是 ${formatJson(COLLAPSIBLE_PANEL_ICON_POSITION)}`,
            {
              expected: formatJson(COLLAPSIBLE_PANEL_ICON_POSITION),
              actual: header.icon_position === undefined ? "undefined" : formatJson(header.icon_position),
            },
        ),
    );
  }

  if (header.icon_expanded_angle !== COLLAPSIBLE_PANEL_ICON_EXPANDED_ANGLE) {
    issues.push(
        collapsiblePanelIconIssue(
            appendPath(headerPath, "icon_expanded_angle"),
            `折叠面板 icon_expanded_angle 必须是 ${COLLAPSIBLE_PANEL_ICON_EXPANDED_ANGLE}`,
            {
              expected: String(COLLAPSIBLE_PANEL_ICON_EXPANDED_ANGLE),
              actual: header.icon_expanded_angle === undefined ? "undefined" : formatJson(header.icon_expanded_angle),
            },
        ),
    );
  }

  return issues;
}

// 图标底座：assets/icon 的图标必须放进主题 icon_surface 底座 interactive_container，不能裸放在分栏或主题底色上
const ICON_MAX_PX = 48;
const ICON_SHELL_SNIPPET =
    '"tag": "interactive_container", "has_border": true, "background_style": "<theme>_icon_surface", "border_color": "<theme>_icon_border"';

// 只认 "24px 24px" / "32px" 这类显式像素宽度；"fill"、"auto" 之类不参与判定
function iconWidthPx(img: JsonObject): number | undefined {
  if (typeof img.size === "string") {
    const match = /^\s*(\d+(?:\.\d+)?)\s*px/.exec(img.size);
    if (match) {
      return Number(match[1]);
    }
  }
  if (typeof img.custom_width === "number") {
    return img.custom_width;
  }
  return undefined;
}

function isIconShell(container: JsonObject | undefined): boolean {
  if (!container || container.tag !== "interactive_container" || container.has_border !== true) {
    return false;
  }
  const background = container.background_style;
  return typeof background === "string" && background !== "" && background !== "default";
}

function describeContainer(container: JsonObject | undefined): string {
  if (!container) {
    return "无容器";
  }
  const tag = typeof container.tag === "string" ? container.tag : "unknown";
  if (tag !== "interactive_container") {
    return `tag=${tag}`;
  }
  const background = typeof container.background_style === "string" ? container.background_style : "undefined";
  return `tag=interactive_container has_border=${formatJson(container.has_border ?? null)} background_style=${background}`;
}

function checkHouseRules(value: JsonValue, path: string, container?: JsonObject): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      issues.push(...checkHouseRules(item, appendPath(path, index), container));
    });
    return issues;
  }

  if (!isRecord(value)) {
    return issues;
  }

  if (value.tag === "markdown" && typeof value.content === "string") {
    issues.push(...checkMarkdownTables(value.content, appendPath(path, "content")));
  }

  // 图标 img 必须被图标底座直接包住；大图、封面图不写 size，天然不受影响
  if (value.tag === "img") {
    const width = iconWidthPx(value);
    if (width !== undefined && width <= ICON_MAX_PX && !isIconShell(container)) {
      issues.push(
          makeIssue(
              path,
              "houseRule/iconShell",
              `图标 img 必须直接放进图标底座容器（${ICON_SHELL_SNIPPET}），底座必须引用主题自己的 *_icon_surface / *_icon_border token；不要把图标裸放在 column、column_set 或主题底色上`,
              { expected: ICON_SHELL_SNIPPET, actual: describeContainer(container) },
          ),
      );
    }
  }

  // 内容列必须 1:1 等分；width:"auto" 的图标槽位不写 weight，天然不受影响
  if (value.tag === "column" && value.weight !== undefined && value.weight !== 1) {
    issues.push(
        makeIssue(
            appendPath(path, "weight"),
            "houseRule/columnWeight",
            "分栏必须 1:1 等分，column.weight 只能是 1；需要主次差异时用字号、留白、背景色表达",
            { expected: "1", actual: formatJson(value.weight) },
        ),
    );
  }

  // 折叠面板必须有统一的折叠箭头 icon，让展开/收起状态可被识别
  if (value.tag === "collapsible_panel") {
    issues.push(...checkCollapsiblePanelIcon(value, path));
  }

  // 带 tag 的节点是子元素的直接容器，用于图标底座判定
  const childContainer = typeof value.tag === "string" ? value : container;
  for (const [key, child] of Object.entries(value)) {
    issues.push(...checkHouseRules(child, appendPath(path, key), childContainer));
  }

  return issues;
}

function formatIssue(issue: ValidationIssue): string {
  const parts = [
    `path=${issue.path}`,
    `property=${issue.property ?? "-"}`,
    `keyword=${issue.keyword}`,
  ];
  if (issue.schemaPath) {
    parts.push(`schemaPath=${issue.schemaPath}`);
  }
  parts.push(`message=${issue.message}`);
  return parts.join(" ");
}

function main(): number {
  let options: CliOptions;
  try {
    options = parseArgs(process.argv.slice(2));
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`错误：${message}`);
    return 2;
  }

  if (options.showHelp) {
    printHelp();
    return 0;
  }

  if (!existsSync(options.schemaPath)) {
    console.error(`错误：schema 文件不存在：${options.schemaPath}`);
    return 2;
  }

  let schema: JsonValue;
  let data: JsonValue;
  try {
    schema = loadJson(options.schemaPath, "schema");
    data = loadJson(options.cardPath, "卡片 JSON");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`错误：${message}`);
    return 1;
  }

  let validator: SchemaValidator;
  try {
    validator = new SchemaValidator(schema);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`错误：${message}`);
    return 2;
  }

  const { target, issues: wrapperIssues } = parseWrapper(data);
  let errors = wrapperIssues;
  if (errors.length === 0) {
    try {
      errors = validator.validate(target.card, target.basePath);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      errors = [makeIssue(target.basePath, "schema", message)];
    }
  }
  if (errors.length === 0) {
    errors = checkHouseRules(target.card, target.basePath);
  }

  if (options.jsonOutput) {
    console.log(
        JSON.stringify(
            {
              valid: errors.length === 0,
              mode: target.mode,
              schema: options.schemaPath,
              errors,
            },
            null,
            2,
        ),
    );
    return errors.length === 0 ? 0 : 1;
  }

  if (errors.length > 0) {
    for (const issue of errors) {
      console.error(`错误：${formatIssue(issue)}`);
    }
    return 1;
  }

  console.log(`通过：有效的 ${target.mode} 互动卡片 JSON`);
  return 0;
}

process.exitCode = main();
