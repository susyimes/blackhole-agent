import { split, toLower } from "no-case";
export function snakeCase(input, options) {
    const lower = toLower(options?.locale);
    return split(input, options).map(lower).join("_");
}
//# sourceMappingURL=index.js.map