import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout.js';
import Dashboard from './pages/Dashboard.js';
import SuiteDetail from './pages/SuiteDetail.js';
import CaseEditor from './pages/CaseEditor.js';
import RunHistory from './pages/RunHistory.js';
import RunDetail from './pages/RunDetail.js';
import Compare from './pages/Compare.js';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/suites/:id" element={<SuiteDetail />} />
          <Route path="/suites/:sid/cases/:cid" element={<CaseEditor />} />
          <Route path="/runs" element={<RunHistory />} />
          <Route path="/runs/:id" element={<RunDetail />} />
          <Route path="/compare" element={<Compare />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
