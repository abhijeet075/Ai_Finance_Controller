import { useEffect, useState } from "react";

import { createReconciliationRun, getHealth } from "./api/client";
import OverviewPage from "./pages/OverviewPage";

function App() {
  const [apiHealthy, setApiHealthy] = useState(false);
  const [sourceBatch, setSourceBatch] = useState("default");
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getHealth()
      .then(() => setApiHealthy(true))
      .catch(() => setApiHealthy(false));
  }, []);

  async function startRun() {
    setLoading(true);
    setError("");
    try {
      setRun(await createReconciliationRun(sourceBatch.trim()));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <OverviewPage
      apiHealthy={apiHealthy}
      sourceBatch={sourceBatch}
      setSourceBatch={setSourceBatch}
      run={run}
      loading={loading}
      error={error}
      startRun={startRun}
    />
  );
}

export default App;
