import { useEffect, useState } from "react";

import { getHealth } from "./api/client";
import OverviewPage from "./pages/OverviewPage";

function App() {
  const [apiHealthy, setApiHealthy] = useState(false);

  useEffect(() => {
    getHealth().then(() => setApiHealthy(true)).catch(() => setApiHealthy(false));
  }, []);

  return <OverviewPage apiHealthy={apiHealthy} />;
}

export default App;
