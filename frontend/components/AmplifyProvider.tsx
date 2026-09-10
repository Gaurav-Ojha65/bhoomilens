"use client";

import { Authenticator } from "@aws-amplify/ui-react";
import "@aws-amplify/ui-react/styles.css";
import { configureAmplify } from "@/lib/amplify-config";
import { useEffect } from "react";

export function AmplifyProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    configureAmplify();
  }, []);
  configureAmplify();

  return (
    <Authenticator hideSignUp>
      {() => <>{children}</>}
    </Authenticator>
  );
}
