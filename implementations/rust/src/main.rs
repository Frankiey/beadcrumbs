mod cli;
mod model;
mod store;
fn main() {
    std::process::exit(cli::main_entry());
}
