import coreWebVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts", "**/*.config.*"] },
  ...coreWebVitals,
  {
    rules: {
      // Two new (react-hooks v6 / React 19) rules that flag correct existing code:
      // - set-state-in-effect: a perf hint that fires on legit on-mount localStorage
      //   syncs and route-change resets.
      // - static-components: false-positives on the dynamic-icon-from-a-map pattern
      //   (`const Icon = map[type]; <Icon />`) — an existing component, not one
      //   created during render.
      // Kept as warnings (advisory, not CI-blocking) so the gate still errors on the
      // rules that matter: rules-of-hooks, next/*, jsx-a11y, undefined refs, etc.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/static-components": "warn",
    },
  },
];

export default eslintConfig;
