import { redirect } from "next/navigation";

/**
 * There is no "home" for an operator — there is the screen they work in.
 * The directory is the only one built, so it is the front door.
 */
export default function Home() {
  redirect("/hotels");
}
