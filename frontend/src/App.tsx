import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import UploadPage from "./pages/UploadPage";
import DashboardPage from "./pages/DashboardPage";
import ProductDetailPage from "./pages/ProductDetailPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<UploadPage />} />
        <Route path="/dashboard/:runId" element={<DashboardPage />} />
        <Route path="/product/:runId/:sku" element={<ProductDetailPage />} />
      </Route>
    </Routes>
  );
}
