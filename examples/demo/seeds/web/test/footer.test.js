import { test } from "node:test";
import assert from "node:assert/strict";
import { renderFooter } from "../src/footer.js";

test("footer renders shop name", () => {
  assert.match(renderFooter(), /Shop/);
});
