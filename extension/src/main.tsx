import React from "react";
import { createRoot } from "react-dom/client";
import * as SDK from "azure-devops-extension-sdk";

import { App } from "./App";
import "./styles.css";

/**
 * The work item form service, declared locally.
 *
 * The azure-devops-extension-api package carries these definitions, but it peers
 * on SDK ^2||^3||^4 and cannot be installed alongside SDK 5. We need exactly one
 * id and one method, so it is not worth pinning the SDK back a major version.
 *
 * Values verified against azure-devops-extension-api@5.276.0:
 * WorkItemTrackingServiceIds.WorkItemFormService and IWorkItemFormService.getId.
 */
const WORK_ITEM_FORM_SERVICE_ID = "ms.vss-work-web.work-item-form";

interface WorkItemFormService {
  getId(): Promise<number>;
}

async function start() {
  // loaded:false means we tell the host when we are actually ready, so the
  // form does not show the panel before it can render.
  await SDK.init({ loaded: false, applyTheme: true });
  await SDK.ready();

  let workItemId: number | undefined;
  try {
    const service = await SDK.getService<WorkItemFormService>(
      WORK_ITEM_FORM_SERVICE_ID
    );
    workItemId = await service.getId();
  } catch {
    // A brand new, unsaved work item has no id yet. The panel still works, it
    // just cannot pin the open item into the context.
  }

  const root = createRoot(document.getElementById("root")!);
  root.render(
    <React.StrictMode>
      <App workItemId={workItemId} />
    </React.StrictMode>
  );

  await SDK.notifyLoadSucceeded();
}

start().catch((error) => {
  SDK.notifyLoadFailed(error instanceof Error ? error : String(error));
});
