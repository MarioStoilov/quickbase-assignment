/**
 * ESLint flat configuration: TypeScript strict rules, React hooks rules, and the
 * naming rules the repository enforces in review.
 */

import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

// Generated output and dependencies are never linted.
const IGNORED_PATHS = ["dist/**", "node_modules/**"];

export default tseslint.config(
  { ignores: IGNORED_PATHS },
  {
    files: ["src/**/*.ts", "src/**/*.tsx", "vite.config.ts"],
    extends: [
      ...tseslint.configs.strictTypeChecked,
      ...tseslint.configs.stylisticTypeChecked,
      reactHooks.configs.flat.recommended,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/explicit-function-return-type": "error",
      "@typescript-eslint/explicit-module-boundary-types": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      "no-restricted-syntax": [
        "error",
        {
          selector: "TSAsExpression:not([typeAnnotation.type='TSTypeReference'])",
          message: "Narrow with a type guard instead of a cast.",
        },
      ],
    },
  },
  {
    // This configuration file runs under Node and is not part of the TypeScript
    // project, so only the untyped rules apply to it.
    files: ["eslint.config.js"],
    extends: [...tseslint.configs.recommended],
    languageOptions: { globals: globals.node },
  },
);
