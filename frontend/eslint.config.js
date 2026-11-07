





import babelParser from "@babel/eslint-parser";
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";


const babel = (jsx) => ({
  parser: babelParser,
  parserOptions: {
    requireConfigFile: false,
    babelOptions: {
      babelrc: false,
      configFile: false,
      parserOpts: { plugins: jsx ? ["typescript", "jsx"] : ["typescript"] },
    },
  },
});

export default [
  { ignores: ["dist/", "coverage/", "src/types/openapi.gen.ts"] },
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { ...babel(false), ecmaVersion: "latest", sourceType: "module", globals: globals.browser },
    plugins: { "react-hooks": reactHooks, "react-refresh": reactRefresh },
    rules: {


      "no-undef": "off",
      "no-unused-vars": "off",
      "no-redeclare": "off",
      "react-hooks/rules-of-hooks": "error",



      "react-hooks/exhaustive-deps": ["error", { additionalHooks: "^useAsync$" }],
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  { files: ["**/*.tsx"], languageOptions: babel(true) },
  {
    files: ["**/*.test.{ts,tsx}", "src/test/**"],
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
    rules: { "react-refresh/only-export-components": "off" },
  },
  {
    files: ["*.{js,mjs}", "scripts/**/*.{js,mjs}", "*.config.ts"],
    languageOptions: { globals: globals.node },
  },
];
