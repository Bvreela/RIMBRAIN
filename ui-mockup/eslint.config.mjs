export default [{
  files: ["**/*.mjs"],
  languageOptions: {
    ecmaVersion: 2022,
    sourceType: "module",
    globals: {
      document: "readonly",
      window: "readonly",
      setTimeout: "readonly",
      clearTimeout: "readonly",
      FormData: "readonly",
      URL: "readonly",
      Blob: "readonly",
    },
  },
  rules: {
    "no-undef": "error",
    "no-unused-vars": "error",
    "no-unreachable": "error",
    "no-duplicate-case": "error",
    "no-constant-condition": "error",
    "eqeqeq": "error",
  },
}];
