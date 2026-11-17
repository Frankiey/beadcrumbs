import { Failure, idPattern, matches, requireValue, textValue } from "./model.js";
import type { Issue } from "./model.js";

export interface IssueCodec {
  accepts(filename: string): boolean;
  filename(id: string): string;
  decode(payload: Uint8Array): unknown;
  encode(issue: Issue): Uint8Array;
}

export function decodeUtf8(payload: Uint8Array): string {
  requireValue(!(payload[0] === 0xef && payload[1] === 0xbb && payload[2] === 0xbf), "UTF-8 BOM is invalid");
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(payload);
  } catch {
    throw new Failure("Invalid UTF-8");
  }
}

// A small strict reader preserves duplicate-key and numeric-lexeme checks
// that JSON.parse discards. Every numeric field in protocol v1 is an integer.
export function decodeJson(payload: Uint8Array): unknown {
  const source = decodeUtf8(payload);
  let offset = 0;
  function whitespace(): void {
    while (offset < source.length && /[ \t\r\n]/.test(source[offset]!)) offset++;
  }
  function string(): string {
    const start = offset++;
    let escaped = false;
    while (offset < source.length) {
      const char = source[offset++]!;
      if (char === '"' && !escaped) {
        const value: unknown = JSON.parse(source.slice(start, offset));
        textValue(value);
        return value;
      }
      escaped = char === "\\" && !escaped;
    }
    throw new Failure("Unterminated JSON string");
  }
  function value(): unknown {
    whitespace();
    const char = source[offset];
    if (char === '"') return string();
    if (char === "{") {
      offset++;
      const result: Record<string, unknown> = Object.create(null);
      whitespace();
      if (source[offset] === "}") { offset++; return result; }
      while (true) {
        whitespace();
        requireValue(source[offset] === '"', "Expected JSON object key");
        const key = string();
        requireValue(!Object.hasOwn(result, key), "Duplicate JSON key: " + key);
        whitespace();
        requireValue(source[offset++] === ":", "Expected colon");
        result[key] = value();
        whitespace();
        const delimiter = source[offset++];
        if (delimiter === "}") return result;
        requireValue(delimiter === ",", "Expected comma");
      }
    }
    if (char === "[") {
      offset++;
      const result: unknown[] = [];
      whitespace();
      if (source[offset] === "]") { offset++; return result; }
      while (true) {
        result.push(value());
        whitespace();
        const delimiter = source[offset++];
        if (delimiter === "]") return result;
        requireValue(delimiter === ",", "Expected comma");
      }
    }
    for (const [word, literal] of [["true", true], ["false", false], ["null", null]] as const) {
      if (source.startsWith(word, offset)) { offset += word.length; return literal; }
    }
    const number = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(source.slice(offset));
    requireValue(number, "Invalid JSON value");
    requireValue(!/[.eE]/.test(number[0]), "Integer fields require integer lexical form");
    offset += number[0].length;
    const parsed = Number(number[0]);
    requireValue(Number.isSafeInteger(parsed), "Integer outside supported range");
    return parsed;
  }
  try {
    const result = value();
    whitespace();
    requireValue(offset === source.length, "Trailing JSON content");
    return result;
  } catch (error) {
    if (error instanceof Failure) throw error;
    throw new Failure("Invalid JSON");
  }
}

export function encodeJson(value: unknown): Uint8Array {
  return Buffer.from(JSON.stringify(value, null, 2) + "\n", "utf-8");
}

export class JsonIssueCodec implements IssueCodec {
  accepts(filename: string): boolean { return filename.endsWith(".json"); }
  filename(id: string): string {
    requireValue(matches(idPattern, id), "Invalid issue ID");
    return id + ".json";
  }
  decode(payload: Uint8Array): unknown { return decodeJson(payload); }
  encode(issue: Issue): Uint8Array { return encodeJson(issue); }
}
